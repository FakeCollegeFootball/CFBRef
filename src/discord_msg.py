from discord_webhook import Webhook

import utils

DISCORD_URL = "https://discordapp.com/api/webhooks/508119756465897473/9_fO3q2tg0ap1964OnQ6zqOa0uaoR4QGUeHzbHe8rYgDR3K16apVS2yvSGVE2Fzu3N-A"

def discordSend(message,title):

    msg = Webhook(DISCORD_URL,color=4169e1)

    msg.set_author(name=title, icon="https://cdn.discordapp.com/emojis/418124751698001920.png")
    msg.set_desc(message)
    msg.set_footer(ts=True)

    print(message)

    msg.post()

def discordFinal(game):

    title = "Final Alert"

    if game.status.winner == game.home.name:
        msg = "\n{} {} - **{} {}**".format(game.away.name,
                                                     game.status.state(False).points,
                                                     game.home.name,
                                                     game.status.state(True).points,
                                                     game.status.quarter,
                                                     utils.renderTime(game.status.clock))
    elif game.status.winner == game.away.name:
        msg = "\n**{} {}** - {} {}".format(game.away.name,
                                                     game.status.state(False).points,
                                                     game.home.name,
                                                     game.status.state(True).points,
                                                     game.status.quarter,
                                                     utils.renderTime(game.status.clock))
    else:
        msg = "Game between {} and {} has ended with no winner".format(game.away.name,game.home.name)

    discordSend(msg,title)

def discordScore(game,message):

    title = "Scoring Alert"

    msg = message

    status = "\n{} {} - {} {} ({}Q {})".format(game.away.name,
                                            game.status.state(False).points,
                                            game.home.name,
                                            game.status.state(True).points,
                                            game.status.quarter,
                                            utils.renderTime(game.status.clock))

    msg += status

    discordSend(msg,title)

def discordTouchdown(game,homeAway):

    msg = "**Touchdown {}!**".format(game.home.name if homeAway == "home" else game.away.name)
    msg = msg.upper()

    discordScore(game,msg)

def discordPAT(game,homeAway):

    msg = "**{} PAT is good**".format(game.home.name if homeAway == "home" else game.away.name)
    msg = msg.upper()

    discordScore(game,msg)

def discordTwoPoint(game,homeAway):

    msg = "**{} two-point conversion is good**".format(game.home.name if homeAway == "home" else game.away.name)
    msg = msg.upper()

    discordScore(game,msg)

def discordSafety(game,homeAway):

    msg = "**{} safety!**".format(game.home.name if homeAway == "home" else game.away.name)
    msg = msg.upper()

    discordScore(game,msg)

def discordFieldGoal(game,homeAway):

    msg = "**{} field goal is good!**".format(game.home.name if homeAway == "home" else game.away.name)
    msg = msg.upper()

    discordScore(game,msg)

# def discordTouchdown(game,homeAway):
#
#     discordSend("**Touchdown {}!**\n{} {} - {} {} ({}Q {})".format(game.home.name if homeAway == "home" else game.away.name,
#                                                                      game.away.name,
#                                                                      game.status.state(False).points,
#                                                                      game.home.name,
#                                                                      game.status.state(True).points,
#                                                                      game.status.quarter,
#                                                                      renderTime(game.status.clock)))
