# koboldai-discordchatbot
Very basic Discord Chatbot Based on Kobold AI

I mostly set this up to mess with my friends in a private discord server, so I wouldn't recommend actually trying to use it for anything serious. The code is probably a mess, so YMMV.

Additional code governing the bot's command and message response logic was taken from:
https://github.com/mishalhossin/Discord-AI-Chatbot

# What it does:

It connects to a locally-hosted KoboldAI/KoboldCPP API backend and serves responses through a Discord bot. It's intended to be used with LLaMA-based LLMs.

The bot will respond to messages that either contain the bot's Discord name, the character name in the definitions file, messages in a defined active channel, or that mention/reply to the bot itself. It will read a SillyTavern format character definition in .json format - stored in the characterfiles folder, however only reads from the name, description, example chat, and initial greeting fields.

The LLaMA sentencepiece tokenizer is used to measure the length of messages for prompt-building purposes. You will need a tokenizer.model file from the LLaMA repository, which should be placed in the tokenizer folder. 

The bot will always keep its character definition data at the top of each prompt sent to the API, and will dynamically determine how many historical messages will be kept in the prompt. Historical messages are stored in memory per user interacting with the bot.

On recieving an API response from Kobold, it will attempt to clean up the text before serving it to Discord.

It will react with a :thinking: emoji to the message being actively responded to and remove it once the response is complete (the Discord API only does fake typing for up to ~10 seconds, but it takes my inferior hardware much longer to get a response from the LLM). It is blocked from trying to respond to other messages while generating a response.

# Commands:

/toggleactive

Admin command - toggles whether the bot will attempt to respond to all messages in a given channel.

/bonk

Resets chat memory