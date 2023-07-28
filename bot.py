import asyncio
import re
import requests
import discord
import sentencepiece as spm
from discord.ext import commands
from dotenv import load_dotenv
import json
import os
import argparse

# Parse args
parser = argparse.ArgumentParser(description="Discord LLM Chatbot")
parser.add_argument("-a", "--api", type = str, help = "API endpoint for generation (kobold or ooba)", default = "kobold")
parser.add_argument("-l", "--length", type = int, help = "Maximum context length", default = 2048)
parser.add_argument("-r", "--react", action = "store_true", help = "React to user messages with an emoji while processing response")
parser.add_argument("-c", "--char", type = str, help = "Path to character file in .json format")
parser.add_argument("-d", "--allowdm", action = "store_true", help = "Allow the bot to respond to DMs")
args = parser.parse_args()
if args.api != "kobold" and args.api != "ooba":
    print("Invalid endpoint (valid options are kobold or ooba)")
    wait = input("Press enter to continue")
    exit()
if args.char is None:
    print("Please specify character file")
    wait = input("Press enter to continue")
    exit()

# Config load
with open('config.json') as config_file:
    config = json.load(config_file)

# Find bot token
load_dotenv()
botToken = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Load tokenizer
sp = spm.SentencePieceProcessor(model_file='tokenizer/tokenizer.model')

# Define API endpoints
if args.api == "kobold":
    web_endpoint = config['ENDPOINT_KOBOLD']
elif args.api == "ooba":
    web_endpoint = config['ENDPOINT_OOBA']
print(f"Using API endpoint: {args.api} at {web_endpoint}")

# Setup character persona
with open(args.char) as char_file:
    cdata = json.load(char_file)
print(f"Using character: {args.char}")

# Keep track of the channels where the bot should be active
active_channels = set()
trigger_words = config['TRIGGER']

# Define globals
message_history = {}
is_responding = False
MAX_RESPONSE = int(config['max_length'])
TEMPERATURE = float(config['temperature'])
TOP_K = int(config['top_k'])
TOP_P = float(config['top_p'])
REP_PEN = float(config['rep_pen'])
context_limit = args.length - MAX_RESPONSE
emoji = "🤔"

# Setup instruct prompt
instructions = config['INSTRUCTIONS']

def generate_kobold(prompt, user):
    try:
        request = {
            "prompt": prompt,
            "use_story": False,
            "use_memory": False,
            "use_authors_note": False,
            "use_world_info": False,
            "max_context_length": args.length,
            "max_length": MAX_RESPONSE,
            "rep_pen": REP_PEN,
            "rep_pen_range": args.length,
            "rep_pen_slope": 0,
            "temperature": TEMPERATURE,
            "tfs": 1,
            "top_a": 0,
            "top_k": TOP_K,
            "top_p": TOP_P,
            "typical": 1,
            "sampler_order": [
                6, 0, 1, 3,
                4, 2, 5
            ],
            "sampler_seed": -1,
            "stop_sequence": [ "You:" , f"{user}:", "###" ]
        }
        response = requests.post(f"{web_endpoint}/api/v1/generate", json=request)
        if response.status_code == 200:
            # Catch no response
            if not response:
                raise
            return response
        else:
            raise
    except requests.exceptions.ConnectionError:
        print("Connection error")
        raise
    except:
        raise

def generate_ooba(prompt, user):
    try:
        request = {
            "prompt": prompt,
            "stopping_strings": [ "You:" , f"{user}:", "###" ],
            "max_new_tokens": MAX_RESPONSE,
            "repetition_penalty": REP_PEN,
            "temperature": TEMPERATURE,
            "top_k": TOP_K,
            "top_p": TOP_P,
            "typical_p": 1,
            "num_beams": 1,
            "seed": -1
        }
        response = requests.post(f"{web_endpoint}/api/v1/generate", json=request)
        # Catch no response
        if not response:
            raise
        return response
    except requests.exceptions.ConnectionError:
        print("Connection error")
        raise
    except:
        raise

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
    global is_responding
    if is_responding:
        return  # Don't respond if busy
    try:
        if message.author.bot:
            return  # Ignore bot's own messages
        if message.reference and message.reference.resolved.author != bot.user:
            return  # Ignore replies to messages
        is_replied = message.reference and message.reference.resolved.author == bot.user
        is_dm_channel = isinstance(message.channel, discord.DMChannel)
        is_active_channel = message.channel.id in active_channels
        is_allowed_dm = args.allowdm and is_dm_channel
        contains_trigger_word = any(word in message.content for word in trigger_words)
        is_bot_mentioned = bot.user.mentioned_in(message)
        bot_name_in_message = (bot.user.name.lower() in message.content.lower()) or (cdata['name'].lower() in message.content.lower())

        if is_active_channel or is_allowed_dm or contains_trigger_word or is_bot_mentioned or is_replied or bot_name_in_message:

            ### Begin response ###
            is_responding = True
            print('Generating response...')
            if args.react:
                await message.add_reaction(emoji)
            
            # Check if current user has any message history, and add the current message to the user's history
            author_id = str(message.author.id)
            if author_id not in message_history:
                message_history[author_id] = []

            # Resolve usernames and emotes
            message_str = message.clean_content
            message_str = re.sub(r"<a?:(\w+):\d+>", r":\1:", message_str)
            message_str = message_str.replace('@','')

            # Add most recent message to the user's history
            message_history[author_id].append(f"{message.author.name}: {message_str}")
        
            # Sub in names in char defs (ST format)
            char_name = cdata['name']
            char_desc = cdata['description'].replace('{{user}}',message.author.name).replace('{{char}}',char_name)
            char_mes = cdata['mes_example'].replace('{{user}}',message.author.name).replace('{{char}}',char_name).replace('<START>','###')
            char_greeting = cdata["first_mes"].replace('{{user}}',message.author.name).replace('{{char}}',char_name)
        
            ### Format prompt ###
            bot_prompt = f"{instructions.replace('{{user}}',message.author.name).replace('{{char}}',char_name)}\n" + \
                         f"{char_desc}\n" + \
                         f"{char_mes}\n" + \
                         f"###\n" + \
                         f"{char_name}: {char_greeting}"

            # Make sure the prompt is not too long
            initial_len = len(sp.encode(f"{bot_prompt}\n\n\n{char_name}:"))
            if initial_len + len(sp.encode(f"{message.author.name}: {message_str}")) >= context_limit:
                message_history[author_id].pop() # Get rid of the last user prompt
                await message.reply("Sorry, something didn't work right.")
                is_responding = False
                print("Your effective context length is too short to handle even a single prompt")
                if args.react:
                    await message.remove_reaction(emoji, message.guild.me)
                return
            current_len = initial_len
            print(f"Base context length is {current_len}.")

            for i in range(len(message_history[author_id])-1, -1, -1):
                current_len = current_len + len(sp.encode(message_history[author_id][i]))
                print(f"Context is {current_len} after {len(message_history[author_id])-i} messages.")
                if current_len >= context_limit:
                    print(f"Context exceeded, removing prior chat messages. Keeping {len(message_history[author_id])-(i+1)} messages.")
                    message_history[author_id] = message_history[author_id][i+1:]
                    break

            # Build final prompt
            user_prompt = "\n".join(message_history[author_id])
            
            prompt = f"{bot_prompt}\n{user_prompt}\n{char_name}:"
            print(f"Prompt:\n{prompt}")

            ### Define the function to send reply ###
            async def send_response(prompt):
                global is_responding
                try:
                    if args.api == "kobold":
                        response = generate_kobold(prompt, message.author.name)
                    elif args.api == "ooba":
                        response = generate_ooba(prompt, message.author.name)
                    result = response.json()['results']
                    print(f"Result:\n{result[0]['text']}")

                    # Clean output
                    text = (result[0]['text'].encode("ascii", "ignore")).decode("ascii")
                    text = text.split(f"{message.author.name}:")
                    text = text[0].strip().replace(f"{char_name}:","").strip()
                    text = text.replace("###","").strip()

                    # Some deprecated cleaning code
                    #text = text.replace("assistant:","").strip()
                    #text = text.replace("### Response:","").strip()
                    #text = text.split("system:")[0]
                    #text = text.split("user:")[0]
                    #text = text.split("### Instruction:")[0]
                        
                    response_text = re.sub('[^.!?:]+$','',text) # Trim incomplete sentences

                    # Catch empty outputs in a very shitty way because I'm not a real developer
                    if len(response_text) < 5:
                        response_text = "Sorry, I didn't get that, could you ask me something else?"
                        message_history[author_id].pop() # Get rid of the last user prompt
                    else:
                        message_history[author_id].append(f"{char_name}: {response_text}") # Add good result to msg history
                    await message.reply(response_text)
                    is_responding = False
                    print("Response complete")
                    if args.react:
                        await message.remove_reaction(emoji, message.guild.me)
                except:
                    message_history[author_id].pop() # Get rid of the last user prompt
                    await message.reply("Sorry, something didn't work right.")
                    is_responding = False
                    print("Unable to generate response")
                    if args.react:
                        await message.remove_reaction(emoji, message.guild.me)

            ### Fake typing and generate response ###
            async with message.channel.typing():
                asyncio.create_task(send_response(prompt))
                    
            await bot.process_commands(message)
    except:
        is_responding = False
        print("An error occurred while attempting to respond to a message")
        return

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
