Telegram Stars payment fix

Changes:
- Uses Telegram Stars currency XTR.
- Omits provider_token for XTR invoices.
- Uses a simple one-time Stars invoice first (no recurring subscription parameter).
- Keeps the configured plan duration when activating the subscription.
- Logs the complete Telegram/API/library invoice error to Render Logs.
- Keeps pre_checkout and successful_payment validation.

Deploy:
1. Replace bot.py and requirements.txt in the Render service.
2. Deploy/restart the service.
3. Open the bot and press the 30 Days / 250 Stars plan.
4. A Telegram Stars invoice should open. You do not need Stars just to test that the invoice opens.
