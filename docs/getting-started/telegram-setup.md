# Telegram Setup

Adjutant communicates through Telegram. You need a bot token and your chat ID.

## Create a bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow the prompts — choose a name and username for your bot
4. BotFather will give you a token that looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` — save it

## Get your chat ID

1. Start a conversation with your new bot (click Start or send any message)
2. Open this URL in your browser, replacing `YOUR_TOKEN` with your token:
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
3. Find `"chat":{"id":123456789}` in the response — that number is your chat ID

## Security notes

- Your bot token is stored in `.env` (never committed to git)
- Only messages from your chat ID are processed — unknown senders are logged and ignored
- Rate limiting (configurable, default 10 messages/min) prevents abuse

## Next step

[Run the setup wizard](setup-wizard.md) to configure Adjutant with your credentials.
