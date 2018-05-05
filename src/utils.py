import logging.handlers
import pickle
import json
import random
import re
import math
import copy
import traceback
from datetime import datetime
from datetime import timedelta

import globals
import database
import wiki
import reddit
import classes
from classes import HomeAway
from classes import Action
from classes import Play
from classes import Result
from classes import QuarterType
from classes import DriveSummary

log = logging.getLogger("bot")


def getLinkToThread(threadID):
	return globals.SUBREDDIT_LINK + threadID


def startGame(homeCoach, awayCoach, startTime=None, location=None, station=None, homeRecord=None, awayRecord=None):
	log.debug("Creating new game between /u/{} and /u/{}".format(homeCoach, awayCoach))

	coachNum, result = verifyCoaches([homeCoach, awayCoach])
	if coachNum != -1:
		log.debug("Coaches not verified, {} : {}".format(coachNum, result))
		return "Something went wrong, someone is no longer an acceptable coach. Please try to start the game again"

	homeTeam = wiki.getTeamByCoach(homeCoach.lower())
	awayTeam = wiki.getTeamByCoach(awayCoach.lower())

	game = newGameObject(homeTeam, awayTeam)
	if startTime is not None:
		game.startTime = startTime
	if location is not None:
		game.location = location
	if station is not None:
		game.station = station
	if homeRecord is not None:
		homeTeam.record = homeRecord
	if awayRecord is not None:
		awayTeam.record = awayRecord

	gameThread = renderGame(game)
	gameTitle = "[GAME THREAD] {}{} @ {}{}".format(
		game.away.name,
		" {}".format(unescapeMarkdown(awayRecord)) if awayRecord is not None else "",
		game.home.name,
		" {}".format(unescapeMarkdown(homeRecord)) if homeRecord is not None else "")

	threadID = str(reddit.submitSelfPost(globals.SUBREDDIT, gameTitle, gameThread))
	game.thread = threadID
	log.debug("Game thread created: {}".format(threadID))

	gameID = database.createNewGame(threadID)
	game.dataID = gameID
	log.debug("Game database record created: {}".format(gameID))

	for user in game.home.coaches:
		database.addCoach(gameID, user, True)
		log.debug("Coach added to home: {}".format(user))
	for user in game.away.coaches:
		database.addCoach(gameID, user, False)
		log.debug("Coach added to away: {}".format(user))

	log.debug("Game started, posting coin toss comment")
	message = "The game has started! {}, you're home. {}, you're away, call **heads** or **tails** in the air.".format(getCoachString(game, True), getCoachString(game, False))
	sendGameComment(game, message, {'action': Action.COIN})
	log.debug("Comment posted, now waiting on: {}".format(game.status.waitingId))
	updateGameThread(game)

	log.debug("Returning game started message")
	return "Game started. Find it [here]({}).".format(getLinkToThread(threadID))


PUBLIC_ENUMS = {
	'Action': Action
}


class EnumEncoder(json.JSONEncoder):
	def default(self, obj):
		for enum in PUBLIC_ENUMS.values():
			if type(obj) is enum:
				return {"__enum__": str(obj)}
		return json.JSONEncoder.default(self, obj)


def as_enum(d):
	if "__enum__" in d:
		name, member = d["__enum__"].split(".")
		return getattr(PUBLIC_ENUMS[name], member)
	else:
		return d


def embedTableInMessage(message, table):
	if table is None:
		return message
	else:
		return "{}{}{})".format(message, globals.datatag, json.dumps(table, cls=EnumEncoder).replace(" ", "%20"))


def extractTableFromMessage(message):
	datatagLocation = message.find(globals.datatag)
	if datatagLocation == -1:
		return None
	data = message[datatagLocation + len(globals.datatag):-1].replace("%20", " ")
	try:
		table = json.loads(data, object_hook=as_enum)
		return table
	except Exception:
		log.debug(traceback.format_exc())
		return None


def verifyCoaches(coaches):
	coachSet = set()
	teamSet = set()
	for i, coach in enumerate(coaches):
		if coach in coachSet:
			return i, 'duplicate'
		coachSet.add(coach)

		team = wiki.getTeamByCoach(coach)
		if team is None:
			return i, 'team'
		if team.name in teamSet:
			return i, 'same'
		teamSet.add(team.name)

		game = database.getGameByCoach(coach)
		if game is not None:
			return i, 'game'

	return -1, None


markdown = [
	{'value': "[", 'result': "%5B"},
	{'value': "]", 'result': "%5D"},
	{'value': "(", 'result': "%28"},
	{'value': ")", 'result': "%29"},
]


def escapeMarkdown(value):
	for replacement in markdown:
		value = value.replace(replacement['value'], replacement['result'])
	return value


def unescapeMarkdown(value):
	for replacement in markdown:
		value = value.replace(replacement['result'], replacement['value'])
	return value


def flair(team):
	return "[{}](#f/{})".format(team.name, team.tag)


def renderTime(time):
	return "{}:{}".format(str(math.trunc(time / 60)), str(time % 60).zfill(2))


def renderGame(game):
	bldr = []

	bldr.append(flair(game.away))
	bldr.append(" **")
	bldr.append(game.away.name)
	bldr.append("** @ ")
	bldr.append(flair(game.home))
	bldr.append(" **")
	bldr.append(game.home.name)
	bldr.append("**\n\n")

	if game.startTime is not None:
		bldr.append(" **Game Start Time:** ")
		bldr.append(unescapeMarkdown(game.startTime))
		bldr.append("\n\n")

	if game.location is not None:
		bldr.append(" **Location:** ")
		bldr.append(unescapeMarkdown(game.location))
		bldr.append("\n\n")

	if game.station is not None:
		bldr.append(" **Watch:** ")
		bldr.append(unescapeMarkdown(game.station))
		bldr.append("\n\n")


	bldr.append("\n\n")

	for homeAway in [False, True]:
		bldr.append(flair(game.team(homeAway)))
		bldr.append("\n\n")
		bldr.append("Total Passing Yards|Total Rushing Yards|Total Yards|Interceptions Lost|Fumbles Lost|Field Goals|Time of Possession|Timeouts\n")
		bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:\n")
		bldr.append("{} yards|{} yards|{} yards|{}|{}|{}/{}|{}|{}".format(
				game.status.stats(homeAway).yardsPassing,
				game.status.stats(homeAway).yardsRushing,
				game.status.stats(homeAway).yardsTotal,
				game.status.stats(homeAway).turnoverInterceptions,
				game.status.stats(homeAway).turnoverFumble,
				game.status.stats(homeAway).fieldGoalsScored,
				game.status.stats(homeAway).fieldGoalsAttempted,
				renderTime(game.status.stats(homeAway).posTime),
				game.status.state(homeAway).timeouts
			)
		)
		bldr.append("\n\n___\n")

	bldr.append("Game Summary|Time\n")
	bldr.append(":-:|:-:\n")
	for drive in []:
		bldr.append("test|test\n")

	bldr.append("\n___\n\n")

	bldr.append("Clock|Quarter|Down|Ball Location|Possession|Playclock|Deadline\n")
	bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:\n")
	bldr.append(renderTime(game.status.clock))
	bldr.append("|")
	bldr.append(str(game.status.quarter))
	bldr.append("|")
	bldr.append(getDownString(game.status.down))
	bldr.append(" & ")
	bldr.append(str(game.status.yards))
	bldr.append("|")
	if game.status.location < 50:
		bldr.append(str(game.status.location))
		bldr.append(" ")
		bldr.append(flair(game.team(game.status.possession)))
	elif game.status.location > 50:
		bldr.append(str(100 - game.status.location))
		bldr.append(" ")
		bldr.append(flair(game.team(game.status.possession.negate())))
	else:
		bldr.append(str(game.status.location))
	bldr.append("|")
	bldr.append(flair(game.team(game.status.possession)))
	bldr.append("|")
	bldr.append(renderDatetime(game.playclock))
	bldr.append("|")
	bldr.append(renderDatetime(game.deadline))

	bldr.append("\n\n___\n\n")

	bldr.append("Team|")
	numQuarters = len(game.status.homeState.quarters)
	for i in range(numQuarters):
		bldr.append("Q")
		bldr.append(str(i + 1))
		bldr.append("|")
	bldr.append("Total\n")
	bldr.append((":-:|"*(numQuarters + 2))[:-1])
	bldr.append("\n")
	for homeAway in [True, False]:
		bldr.append(flair(game.team(homeAway)))
		bldr.append("|")
		for quarter in game.status.state(homeAway).quarters:
			bldr.append(str(quarter))
			bldr.append("|")
		bldr.append("**")
		bldr.append(str(game.status.state(homeAway).points))
		bldr.append("**\n")

	return ''.join(bldr)


def coinToss():
	return random.choice([True, False])


def playNumber():
	return random.randint(0, 1500)


def saveGameObject(game):
	file = open("{}/{}".format(globals.SAVE_FOLDER_NAME, game.thread), 'wb')
	pickle.dump(game, file)
	file.close()


def loadGameObject(threadID):
	try:
		file = open("{}/{}".format(globals.SAVE_FOLDER_NAME, threadID), 'rb')
	except FileNotFoundError as err:
		log.warning("Game file doesn't exist: {}".format(threadID))
		return None
	game = pickle.load(file)
	file.close()
	return game


# def getGameByThread(thread):
# 	threadText = reddit.getSubmission(thread).selftext
# 	return extractTableFromMessage(threadText)


def getGameByUser(user):
	dataGame = database.getGameByCoach(user)
	if dataGame is None:
		return None
	game = loadGameObject(dataGame['thread'])
	game.dataID = dataGame['id']
	game.thread = dataGame['thread']
	game.errored = dataGame['errored']
	return game


# def getGameThreadText(game):
# 	threadText = renderGame(game)
# 	return embedTableInMessage(threadText, game)


def updateGameThread(game):
	updateGameTimes(game)
	if game.thread is None:
		log.error("No thread ID in game when trying to update")
	game.dirty = False
	saveGameObject(game)
	threadText = renderGame(game)
	reddit.editThread(game.thread, threadText)


def coachHomeAway(game, coach):
	if coach.lower() in game.home.coaches:
		return HomeAway(True)
	elif coach.lower() in game.away.coaches:
		return HomeAway(False)
	else:
		return None


def sendGameMessage(isHome, game, message, dataTable):
	reddit.sendMessage(game.team(isHome).coaches,
	                   "{} vs {}".format(game.home.name, game.away.name),
	                   embedTableInMessage(message, dataTable))
	return reddit.getRecentSentMessage().id


def sendGameComment(game, message, dataTable=None, saveWaiting=True):
	commentResult = reddit.replySubmission(game.thread, embedTableInMessage(message, dataTable))
	if saveWaiting:
		game.status.waitingId = commentResult.fullname
	log.debug("Game comment sent, now waiting on: {}".format(game.status.waitingId))
	return commentResult


def getRange(rangeString):
	rangeEnds = re.findall('(\d+)', rangeString)
	if len(rangeEnds) < 2 or len(rangeEnds) > 2:
		return None, None
	return int(rangeEnds[0]), int(rangeEnds[1])


def getLinkFromGameThing(threadId, thingId):
	if thingId.startswith("t1"):
		waitingMessageType = "comment"
		link = "{}//{}".format(getLinkToThread(threadId), thingId[3:])
	elif thingId.startswith("t4"):
		waitingMessageType = "message"
		link = "{}{}".format(globals.MESSAGE_LINK, thingId[3:])
	else:
		return "Something went wrong. Not valid thingid: {}".format(thingId)

	return "[{}]({})".format(waitingMessageType, link)


def isGameWaitingOn(game, user, action, messageId):
	if game.status.waitingAction != action:
		log.debug("Not waiting on {}: {}".format(action, game.status.waitingAction))
		return "I'm not waiting on a {} for this game, are you sure you replied to the right message?".format(action)

	if (game.status.waitingOn == 'home') != coachHomeAway(game, user):
		log.debug("Not waiting on message author's team")
		return "I'm not waiting on a message from you, are you sure you responded to the right message?"

	if game.status.waitingId is not None and game.status.waitingId != messageId:
		log.debug("Not waiting on message id: {} : {}".format(game.status.waitingId, messageId))

		link = getLinkFromGameThing(game.thread, game.status.waitingId)

		if messageId.startswith("t1"):
			messageType = "comment"
		elif messageId.startswith("t4"):
			messageType = "message"
		else:
			return "Something went wrong. Not valid: {}".format(game.status.waitingId)

		return "I'm not waiting on a reply to this {}. Please respond to this {}".format(messageType, link)

	return None


def getCoachString(game, isHome):
	bldr = []
	for coach in game.team(isHome).coaches:
		bldr.append("/u/{}".format(coach))
	return " and ".join(bldr)


def getNthWord(number):
	if number == 1:
		return "1st"
	elif number == 2:
		return "2nd"
	elif number == 3:
		return "3rd"
	elif number == 4:
		return "4th"
	else:
		return "{}th".format(number)


def getDownString(down):
	if down >= 1 and down <= 4:
		return getNthWord(down)
	else:
		log.warning("Hit a bad down number: {}".format(down))
		return "{}".format(down)


def getLocationString(game):
	location = game.status.location
	offenseTeam = game.team(game.status.possession).name
	defenseTeam = game.team(game.status.possession.negate()).name
	if location <= 0 or location >= 100:
		log.warning("Bad location: {}".format(location))
		return str(location)

	if location == 0:
		return "{} goal line".format(offenseTeam)
	if location < 50:
		return "{} {}".format(offenseTeam, location)
	elif location == 50:
		return str(location)
	else:
		return "{} {}".format(defenseTeam, 100 - location)


def getCurrentPlayString(game):
	if game.status.waitingAction == Action.CONVERSION:
		return "{} just scored.".format(game.team(game.status.possession).name)
	elif game.status.waitingAction == Action.KICKOFF:
		return "{} is kicking off".format(game.team(game.status.possession).name)
	else:
		return "It's {} and {} on the {}.".format(
			getDownString(game.status.down),
			"goal" if game.status.location + game.status.yards >= 100 else game.status.yards,
			getLocationString(game)
		)


def getWaitingOnString(game):
	string = "Error, no action"
	if game.status.waitingAction == Action.COIN:
		string = "Waiting on {} for coin toss".format(game.team(game.status.waitingOn).name)
	elif game.status.waitingAction == Action.DEFER:
		string = "Waiting on {} for receive/defer".format(game.team(game.status.waitingOn).name)
	elif game.status.waitingAction == Action.KICKOFF:
		string = "Waiting on {} for kickoff number".format(game.team(game.status.waitingOn).name)
	elif game.status.waitingAction == Action.PLAY:
		if game.status.waitingOn == game.status.possession:
			string = "Waiting on {} for an offensive play".format(game.team(game.status.waitingOn).name)
		else:
			string = "Waiting on {} for a defensive number".format(game.team(game.status.waitingOn).name)

	return string


def sendDefensiveNumberMessage(game):
	defenseHomeAway = game.status.possession.negate()
	log.debug("Sending get defence number to {}".format(getCoachString(game, defenseHomeAway)))
	reddit.sendMessage(game.team(defenseHomeAway).coaches,
	                   "{} vs {}".format(game.away.name, game.home.name),
	                   embedTableInMessage("{}\n\nReply with a number between **1** and **1500**, inclusive."
	                                       .format(getCurrentPlayString(game)), {'action': game.status.waitingAction}))
	messageResult = reddit.getRecentSentMessage()
	game.status.waitingId = messageResult.fullname
	log.debug("Defensive number sent, now waiting on: {}".format(game.status.waitingId))


def extractPlayNumber(message):
	numbers = re.findall('(\d+)', message)
	if len(numbers) < 1:
		log.debug("Couldn't find a number in message")
		return -1, "It looks like you should be sending me a number, but I can't find one in your message."
	if len(numbers) > 1:
		log.debug("Found more than one number")
		return -1, "It looks like you puts more than one number in your message"

	number = int(numbers[0])
	if number < 1 or number > 1500:
		log.debug("Number out of range: {}".format(number))
		return -1, "I found {}, but that's not a valid number.".format(number)

	return number, None


def setLogGameID(threadId, game):
	globals.game = game
	globals.logGameId = " {}:".format(threadId)


def clearLogGameID():
	globals.game = None
	globals.logGameId = ""


def findKeywordInMessage(keywords, message):
	found = []
	for keyword in keywords:
		if isinstance(keyword, list):
			for actualKeyword in keyword:
				if actualKeyword in message:
					found.append(keyword[0])
					break
		else:
			if keyword in message:
				found.append(keyword)

	if len(found) == 0:
		return 'none'
	elif len(found) > 1:
		log.debug("Found multiple keywords: {}".format(', '.join(found)))
		return 'mult'
	else:
		return found[0]


def listSuggestedPlays(game):
	if game.status.waitingAction == Action.CONVERSION:
		return "**PAT** or **two point**"
	elif game.status.waitingAction == Action.KICKOFF:
		return "**normal**, **squib** or **onside**"
	else:
		if game.status.down == 4:
			if game.status.location > 62:
				return "**field goal**, or go for it with **run** or **pass**"
			elif game.status.location > 57:
				return "**punt** or **field goal**, or go for it with **run** or **pass**"
			else:
				return "**punt**, or go for it with **run** or **pass**"
		else:
			return "**run** or **pass**"


def buildMessageLink(recipient, subject, content):
	return "https://np.reddit.com/message/compose/?to={}&subject={}&message={}".format(
		recipient,
		subject.replace(" ", "%20"),
		content.replace(" ", "%20")
	)


def addStatRunPass(game, runPass, amount):
	if runPass == Play.RUN:
		addStat(game, 'yardsRushing', amount)
	elif runPass == Play.PASS:
		addStat(game, 'yardsPassing', amount)
	else:
		log.warning("Error in addStatRunPass, invalid play: {}".format(runPass))


def addStat(game, stat, amount, offenseHomeAway=None):
	if offenseHomeAway is None:
		offenseHomeAway = game.status.possession
	log.debug("Adding stat {} : {} : {} : {}".format(stat, offenseHomeAway, getattr(game.status.stats(offenseHomeAway), stat), amount))
	setattr(game.status.stats(offenseHomeAway), stat, getattr(game.status.stats(offenseHomeAway), stat) + amount)
	if stat in ['yardsPassing', 'yardsRushing']:
		game.status.stats(offenseHomeAway).yardsTotal += amount


def isGameOvertime(game):
	return game.status.quarterType in [QuarterType.OVERTIME_NORMAL, QuarterType.OVERTIME_TIME]


def updateGameTimes(game):
	game.playclock = database.getGamePlayed(game.dataID)
	game.deadline = database.getGameDeadline(game.dataID)


def renderDatetime(dtTm):
	return dtTm.strftime("%m/%d %I:%M UTC")


def cycleStatus(game, messageId):
	oldStatus = copy.deepcopy(game.status)
	oldStatus.messageId = messageId
	game.previousStatus.insert(0, oldStatus)
	if len(game.previousStatus) > 3:
		game.previousStatus.pop()


def newGameObject(home, away):
	return classes.Game(home, away)


def newDebugGameObject():
	home = classes.Team(tag="team1", name="Team 1", offense=classes.OffenseType.OPTION, defense=classes.DefenseType.THREE_FOUR)
	home.coaches.append("watchful1")
	away = classes.Team(tag="team2", name="Team 2", offense=classes.OffenseType.SPREAD, defense=classes.DefenseType.FOUR_THREE)
	away.coaches.append("watchful12")
	return classes.Game(home, away)


def renderGameStatusMessage(game):
	bldr = []
	bldr.append("[Game](")
	bldr.append(globals.SUBREDDIT_LINK)
	bldr.append(globals.logGameId[1:-1])
	bldr.append(") errored.\n\n")
	bldr.append("Status|Waiting|Link\n")
	bldr.append(":-:|:-:|:-:\n")

	for i, status in enumerate(globals.game.previousStatus):
		bldr.append(status.possession.name())
		bldr.append("/")
		bldr.append(globals.game.team(status.possession).name)
		bldr.append(" with ")
		bldr.append(getNthWord(status.down))
		bldr.append(" & ")
		bldr.append(str(status.yards))
		bldr.append(" on the ")
		bldr.append(str(status.location))
		bldr.append(" with ")
		bldr.append(renderTime(status.clock))
		bldr.append(" in the ")
		bldr.append(getNthWord(status.quarter))
		bldr.append("|")
		bldr.append(getLinkFromGameThing(globals.game.thread, status.waitingId))
		bldr.append(" ")
		bldr.append(status.waitingOn.name())
		bldr.append("/")
		bldr.append(globals.game.team(status.waitingOn).name)
		bldr.append(" for ")
		bldr.append(status.waitingAction.name)
		bldr.append("|")
		bldr.append("[Message](")
		bldr.append(buildMessageLink(
                    globals.ACCOUNT_NAME,
                    "Kick game",
                    "kick {} {}".format(globals.game.thread, i)
                ))
		bldr.append(")")

	return ''.join(bldr)


driveEnders = [Result.TURNOVER, Result.TOUCHDOWN, Result.TURNOVER_TOUCHDOWN, Result.FIELD_GOAL, Result.PUNT]


# def getDrives(game):
# 	drives = []
# 	drive = None
# 	for i, playSummary in enumerate(game.plays):
# 		if playSummary in classes.kickoffPlays:
#
#
# 		if playSummary not in classes.kickoffPlays and playSummary.posHome != previousPlay.posHome:
#
#
# 		if drive is None:
# 			drive = DriveSummary()
# 			drive.posHome = playSummary.posHome
# 		if playSummary.yards is not None:
# 			drive.yards += playSummary.yards
# 		drive.time += playSummary.time
#
#
# 		if playSummary.result in driveEnders:
# 			drives.append(drive)
# 			print(drive)
# 			drive = None
#
# 		previousPlay = playSummary
