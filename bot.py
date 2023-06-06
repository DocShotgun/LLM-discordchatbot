import asyncio
import re
import requests
import discord
import sentencepiece as spm
from discord.ext import commands
from dotenv import load_dotenv
import json
import os

# Find bot token
load_dotenv()
botToken = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Load tokenizer
sp = spm.SentencePieceProcessor(model_file='tokenizer/tokenizer.model')

# Config load
with open('config.json') as config_file:
    config = json.load(config_file)

# Define KoboldCPP API endpoint
web_endpoint = "http://127.0.0.1:5001"

# Setup character persona
character_list = []

for nfile in os.listdir("characterfiles"):
    if nfile.endswith('.json'):
        with open(os.path.join("characterfiles", nfile)) as f:
            character_data = json.load(f)
            character_list.append(character_data)

if len(character_list) == 1:
    cdata = character_list[0]

# Keep track of the channels where the bot should be active
allow_dm = False
active_channels = set()
trigger_words = config['TRIGGER']

# Define limits
message_history = {}
is_responding = False
MAX_TOKENS = 1900
emoji = "🤔"

# Setup instruct prompt
instructions = config['INSTRUCTIONS']

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} aka {bot.user.name} has connected to Discord!")

    invite_link = discord.utils.oauth_url(
        bot.user.id,
        permissions=discord.Permissions(),
        scopes=("bot", "applications.commands")
    )
    print(f"Invite link: {invite_link}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return  # Ignore bot's own messages
    if message.reference and message.reference.resolved.author != bot.user:
        return  # Ignore replies to messages
    global is_responding
    if is_responding:
        return  # Don't respond if busy
    
    is_replied = message.reference and message.reference.resolved.author == bot.user
    is_dm_channel = isinstance(message.channel, discord.DMChannel)
    is_active_channel = message.channel.id in active_channels
    is_allowed_dm = allow_dm and is_dm_channel
    contains_trigger_word = any(word in message.content for word in trigger_words)
    is_bot_mentioned = bot.user.mentioned_in(message)
    bot_name_in_message = (bot.user.name.lower() in message.content.lower()) or (cdata['name'].lower() in message.content.lower())

    if is_active_channel or is_allowed_dm or contains_trigger_word or is_bot_mentioned or is_replied or bot_name_in_message:

        # Begin response
        is_responding = True
        print('Generating response...')
        await message.add_reaction(emoji)
        
        # Check if current user has any message history, and add the current message to the user's history
        author_id = str(message.author.id)
        if author_id not in message_history:
            message_history[author_id] = []

        # Resolve usernames and emotes
        message_str = message.clean_content
        message_str = re.sub(r"<a?:(\w+):\d+>", r":\1:", message_str)

        # Add most recent message to the user's history
        message_history[author_id].append(f"{message.author.name}: {message_str}")
    
        # Sub in names in char defs (ST format)
        char_name = cdata['name']
        char_desc = cdata['description'].replace('{{user}}',message.author.name).replace('{{char}}',char_name)
        char_mes = cdata['mes_example'].replace('{{user}}',message.author.name).replace('{{char}}',char_name).replace('<START>',f'This is how {char_name} should speak:')
        char_greeting = cdata["first_mes"].replace('{{user}}',message.author.name).replace('{{char}}',char_name)
    
        ### Format prompt ###
        bot_prompt = f"{instructions.replace('{{user}}',message.author.name).replace('{{char}}',char_name)}\n" + \
                     f"{char_name}'s Persona: {char_desc}\n" + \
                     f"{char_mes}\n" + \
                     f"And now the roleplay chat between {message.author.name} and {char_name} begins:\n" + \
                     f"{char_name}: {char_greeting}"

        # Make sure the prompt is not too long
        initial_len = len(sp.encode(f"{bot_prompt}\n\n\n{char_name}: "))
        current_len = initial_len
        print(f"Base context length is {current_len}.")

        for i in range(len(message_history[author_id])-1, -1, -1):
            current_len = current_len + len(sp.encode(message_history[author_id][i]))
            print(f"Context is {current_len} after {len(message_history[author_id])-i} messages.")
            if current_len >= MAX_TOKENS:
                print(f"Context exceeded, removing prior chat messages. Keeping {len(message_history[author_id])-(i+1)} messages.")
                message_history[author_id] = message_history[author_id][i+1:]
                break

        # Build final prompt
        user_prompt = "\n".join(message_history[author_id])
        
        prompt = f"{bot_prompt}\n{user_prompt}\n{char_name}: "

        # Define the function to generate responses from API
        async def send_response(prompt):
            global is_responding
            try:
                request = {
                    "prompt": prompt,
                    "use_story": False,
                    "use_memory": False,
                    "use_authors_note": False,
                    "use_world_info": False,
                    "max_context_length": 2048,
                    "max_length": 100,
                    "rep_pen": 1.1,
                    "rep_pen_range": 2048,
                    "rep_pen_slope": 0.3,
                    "temperature": 0.59,
                    "tfs": 0.87,
                    "top_a": 0,
                    "top_k": 0,
                    "top_p": 1,
                    "typical": 1,
                    "sampler_order": [
                        5, 0, 2, 3,
                        1, 4, 6
                    ]
                }
                response = requests.post(f"{web_endpoint}/api/v1/generate", json=request)
                if response.status_code == 200:
                    result = response.json()['results']

                    # Clean output
                    text = (result[0]['text']).split(f"{message.author.name}:")
                    text = text[0].strip().replace(f"{char_name}:","").strip()
                    text = text.replace("assistant:","").strip()
                    text = text.replace("### Response:","").strip()

                    text = text.split("system:")[0]
                    text = text.split("user:")[0]
                    text = text.split("### Instruction:")[0]
                    
                    response_text = re.sub('[^.!?:]+$','',text) # Trim incomplete sentences

                    # Catch empty outputs in a very shitty way because I'm not a real developer
                    if len(response_text) < 5:
                        response_text = "Sorry, I didn't get that, please try again."
                        message_history[author_id].pop() # Get rid of the last user prompt
                    else:
                        message_history[author_id].append(f"\n{char_name}: {response_text}") # Add good result to msg history
                    
                    await message.reply(response_text)
                    is_responding = False
                    print("...Response complete.")
                    await message.remove_reaction(emoji, message.guild.me)
                else:
                    message_history[author_id].pop() # Get rid of the last user prompt
                    await message.reply("Sorry, something didn't work right.")
                    is_responding = False
                    print("...Unable to retrieve response")
                    await message.remove_reaction(emoji, message.guild.me)
                
            except requests.exceptions.ConnectionError:
                message_history[author_id].pop() # Get rid of the last user prompt
                await message.reply("Sorry, something didn't work right.")
                is_responding = False
                print("...Endpoint error")
                await message.remove_reaction(emoji, message.guild.me)

        # Fake typing and generate response
        async with message.channel.typing():
                asyncio.create_task(send_response(prompt))
                
        #await bot.process_commands(message)

#@bot.hybrid_command(name="toggledm", description="Toggle DMs")
#@commands.has_permissions(administrator=True)
#async def toggledm(ctx):
#    global allow_dm
#    allow_dm = not allow_dm
#    message = await ctx.send(f"DMs are now {'on' if allow_dm else 'off'}.")
#    await asyncio.sleep(3)
#    await message.delete()

@bot.hybrid_command(name="toggleactive", description="Toggle Active Channel")
@commands.has_permissions(administrator=True)
async def toggleactive(ctx):
    channel_id = ctx.channel.id
    if channel_id in active_channels:
        active_channels.remove(channel_id)
        with open("channels.txt", "w") as f:
            for id in active_channels:
                f.write(str(id) + "\n")
        message = await ctx.send(
            f"{ctx.channel.mention} 'Channel disabled.'"
        )
        await asyncio.sleep(3)
        await message.delete()
    else:
        active_channels.add(channel_id)
        with open("channels.txt", "a") as f:
            f.write(str(channel_id) + "\n")
        message = await ctx.send(
            f"{ctx.channel.mention} 'Channel enabled.'")
        await asyncio.sleep(3)
        await message.delete()


# Read the active channels from channels.txt on startup
if os.path.exists("channels.txt"):
    with open("channels.txt", "r") as f:
        for line in f:
            channel_id = int(line.strip())
            active_channels.add(channel_id)


@bot.hybrid_command(name="bonk", description="Reset message history")
async def bonk(ctx):
    message_history.clear()  # Reset the message history dictionary
    message = await ctx.send("Message history reset.")
    await asyncio.sleep(3)
    await message.delete()


# Run the bot using your bot token
bot.run(botToken)
