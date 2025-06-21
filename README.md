# Telegram Channel Verification Bot

Isang Telegram bot na nag-ve-verify ng mga users na gusto sumali sa private channels/groups. Ginawa para sa secure at automated na verification process.

## Features

- 🔐 **Automated Verification**: Automatic na nag-de-detect ng join requests
- 📱 **Contact Verification**: Kailangan i-share ng user ang contact info
- 🔢 **Code Input Interface**: Interactive numeric keypad para sa verification code
- 👨‍💼 **Admin Monitoring**: Real-time notifications at statistics para sa admin
- 🛡️ **Security**: Secure verification process na hindi pwedeng i-bypass
- 📊 **Database Tracking**: SQLite database para sa verified users at pending requests

## Paano Gumagana

1. **User mag-request sa private channel** - Bot automatically ma-de-detect
2. **Bot mag-send ng private message** - Asking for contact verification
3. **User mag-share ng contact** - Using Telegram's contact sharing feature
4. **Bot mag-send ng verification code** - 6-digit code (sa production, ma-se-send via SMS)
5. **User mag-input ng code** - Using interactive number buttons
6. **Auto-approve pag correct** - Automatic approval sa channel

## Setup Instructions

### 1. Create Telegram Bot

1. Message si [@BotFather](https://t.me/botfather) sa Telegram
2. Send `/newbot` at sundin ang instructions
3. Save ang Bot Token na makakuha mo

### 2. Get Your Admin ID

1. Message si [@userinfobot](https://t.me/userinfobot)
2. I-copy ang User ID mo (hindi na kailangan since naka-set na sa code: `5521402866`)

### 3. Setup Channel

1. Create private channel o group
2. Add ang bot as admin with permissions:
   - "Invite users via link"
   - "Add new admins" 
3. I-copy ang channel username (e.g., @your_channel)

### 4. Deploy sa Railway

1. **Fork this repository** sa GitHub
2. **Connect Railway sa GitHub account** mo
3. **Create new project** sa Railway
4. **Connect** sa forked repository
5. **Add environment variables**:
   ```
   BOT_TOKEN=your_bot_token_here
   ADMIN_ID=5521402866
   CHANNEL_ID=@your_channel_username
   ```
6. **Deploy!**

### Environment Variables

Sa Railway, i-set ang mga sumusunod na environment variables:

- `BOT_TOKEN`: Ang bot token na nakuha mo from BotFather
- `ADMIN_ID`: `5521402866` (already set sa code)
- `CHANNEL_ID`: Ang username o ID ng channel (e.g., `@mychannel` o `-1001234567890`)

## File Structure

```
telegram-verification-bot/
│
├── bot.py              # Main bot code
├── requirements.txt    # Python dependencies
├── Dockerfile         # Docker configuration
├── README.md          # Documentation
└── verification.db    # SQLite database (auto-created)
```

## Admin Commands

- `/start` - Welcome message
- `/stats` - Show verification statistics (admin only)

## Database Tables

### pending_verifications
- `user_id` - Telegram User ID
- `username` - Telegram username
- `first_name` - User's first name
- `phone_number` - Shared contact number
- `verification_code` - 6-digit verification code
- `timestamp` - Request timestamp
- `status` - Verification status

### verified_users
- `user_id` - Telegram User ID
- `username` - Telegram username
- `first_name` - User's first name
- `phone_number` - Verified contact number
- `verified_date` - Verification completion date

## Security Features

1. **Contact Verification**: User must share their own contact info
2. **Code Generation**: Random 6-digit verification codes
3. **Session Management**: Temporary verification sessions
4. **Admin Monitoring**: All activities logged at monitored
5. **Database Logging**: Complete audit trail

## Troubleshooting

### Common Issues

1. **Bot not responding to join requests**
   - Make sure bot is admin sa channel
   - Check if `CHANNEL_ID` is correct
   - Verify bot has "Invite users via link" permission

2. **Users not receiving private messages**
   - User must start a conversation with the bot first
   - Bot automatically sends message when join request is detected

3. **Verification code not working**
   - Sa demo version, code is shown directly
   - Sa production, i-integrate sa SMS API

### Error Monitoring

Admin makakakuha ng notifications para sa:
- New join requests
- Contact sharing
- Verification completions
- System errors

## Production Recommendations

Para sa production use:

1. **SMS Integration**: I-integrate ang SMS API para sa real verification codes
2. **Rate Limiting**: I-add ang rate limiting para prevent spam
3. **Database Backup**: I-setup ang automated database backups
4. **Monitoring**: I-add ang proper monitoring at alerting
5. **Logging**: Enhanced logging para sa security audits

## License

MIT License - Feel free to modify at gamitin!

## Support

Para sa questions o issues, create lang ng GitHub issue o contact the developer.

---

**Note**: Ito ay demo version. Sa production, ang verification code ay dapat ma-send through SMS o ibang secure method, hindi displayed sa chat.
