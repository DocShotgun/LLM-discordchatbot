# LLM-discordchatbot
Very basic Discord Chatbot for local LLM inference

I mostly set this up to mess with my friends in a private discord server, so I wouldn't recommend actually trying to use it for anything serious. The code is probably a mess, so YMMV.

Additional code governing the bot's command and message response logic was taken from:
https://github.com/mishalhossin/Discord-AI-Chatbot

# What it does:

It connects to a locally-hosted KoboldAI/KoboldCPP/Oobabooga API backend and serves responses through a Discord bot. It's intended to be used with Llama-based LLMs.

The bot will respond to messages that either contain the bot's Discord name, the character name in the definitions file, messages in a defined active channel, or that mention/reply to the bot itself. It will read a SillyTavern format character definition in .json format - stored in the characterfiles folder, however only reads from the name, description, example chat, and initial greeting fields.

The Llama sentencepiece tokenizer is used to measure the length of messages for prompt-building purposes. You will need a tokenizer.model file from the Llama repository, which should be placed in the tokenizer folder. 

The bot will always keep its character definition data at the top of each prompt sent to the API, and will dynamically determine how many historical messages will be kept in the prompt. Historical messages are stored in memory per user interacting with the bot.

On recieving an API response from Kobold/Ooba, it will attempt to clean up the text before serving it to Discord.

# How to use (for the brave):

Requirements: Python 3.10 and Git

Installation:
1. Install and configure one of KoboldAI (https://github.com/henk717/KoboldAI), KoboldCPP (https://github.com/LostRuins/koboldcpp), or Oobabooga textgen webui (https://github.com/oobabooga/text-generation-webui).   
2. Clone this repository to your desired location: ```git clone https://github.com/DocShotgun/LLM-discordchatbot```
3. Open a terminal inside the LLM-discordchatbot folder and create a virtual environment: ```python -m venv venv```
4. Activate the virtual environment: ```./venv/scripts/activate```
5. Install dependencies: ```pip install -r requirements.txt```
6. Register an application on Discord, create a bot, and obtain your bot token: https://discord.com/developers/docs/intro
7. Edit ".env" with your Discord bot token.
8. Obtain a "tokenizer.model" file from a Llama model and place it inside the tokenizer folder. The official HuggingFace repository can be found at: https://huggingface.co/meta-llama
9. Obtain a TavernAI/SillyTavern character card in .json format and place it in the characterfiles folder. Or create your own at: https://avakson.github.io/character-editor/
10. Edit your settings in "config.json" and "start.bat".
11. Start your API endpoint (KoboldAI, KoboldCPP, or Oobabooga textgen webui).
12. Run "start.bat"!

# Commandline args:

--api (-a): Which API backend to use; select "kobold" or "ooba"

--length (-l): Max context length of the model (2048 for Llama 1, 4096 for Llama 2)

--react (-r): React with a :thinking: emoji to the message being actively responded to and remove it once the response is complete (the Discord API only does fake typing for up to ~10 seconds, but it takes my inferior hardware much longer to get a response from the LLM). It is blocked from trying to respond to other messages while generating a response.

--char (-c): Path to the character definition .json

--allowdm (-d): Allow the bot to respond to DMs

# Commands:

/toggleactive

Admin command - toggles whether the bot will attempt to respond to all messages in a given channel.

/bonk

Resets chat memory
