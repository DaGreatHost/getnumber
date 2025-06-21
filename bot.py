import logging
import random
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
CHANNEL_ID = os.getenv('CHANNEL_ID', '-1002565132160')

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
                status TEXT DEFAULT 'pending',
                admin_notified BOOLEAN DEFAULT 0
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
        """Start command handler - Now includes contact sharing"""
        user = update.message.from_user
        
        welcome_text = f"""
🤖 **Channel Verification Bot**

Hello {user.first_name}! I will help you get verified to join our private channel/group.

**How it works:**
1. Share your contact number that you use for your Telegram account
2. You'll receive a 5-digit verification code via Telegram
3. Enter the code using the number buttons
4. Once verified, you can join the channel!

**Step 1:** Please share your contact number by clicking the button below.

👇 Click the button to share your contact info.
        """
        
        # Create contact sharing button
        contact_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("📱 Share My Contact", request_contact=True)]
        ], resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            welcome_text, 
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

    async def handle_join_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new join requests to the channel"""
        try:
            user = update.chat_join_request.from_user
            chat = update.chat_join_request.chat
            
            # Log the join request
            logger.info(f"New join request from {user.first_name} (@{user.username}) to {chat.title}")
            
            # Check if user is already verified
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM verified_users WHERE user_id = ?', (user.id,))
            if cursor.fetchone():
                # User is already verified, approve immediately
                await context.bot.approve_chat_join_request(chat.id, user.id)
                await context.bot.send_message(
                    user.id,
                    "✅ **Welcome back!**\n\nYou're already verified. Your join request has been approved! 🎉",
                    parse_mode='Markdown'
                )
                return
            
            # Notify admin about the join request
            admin_message = f"""
🔔 **New Join Request**

👤 **User:** {user.first_name} (@{user.username})
🆔 **User ID:** `{user.id}`
📢 **Channel:** {chat.title}
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

User needs to complete verification process first.
            """
            await context.bot.send_message(ADMIN_ID, admin_message, parse_mode='Markdown')
            
            # Send verification message to user
            verification_message = f"""
🔐 **Verification Required**

Hello {user.first_name}! 

I noticed you requested to join **{chat.title}**. To get approved, please start the verification process.

Please click /start to begin verification.
            """
            
            await context.bot.send_message(user.id, verification_message, parse_mode='Markdown')
            
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
                    "❌ You need to share your own contact info, not someone else's.",
                    reply_markup=ReplyKeyboardRemove()
                )
                return
            
            # Update database with phone number
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO pending_verifications 
                (user_id, username, first_name, phone_number, timestamp, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user.id, user.username, user.first_name, contact.phone_number, datetime.now(), 'contact_shared'))
            self.conn.commit()
            
            # Send confirmation to user
            await update.message.reply_text(
                f"""
✅ **Contact Received!**

📱 **Phone:** {contact.phone_number}

⏳ **Next Step:** Please wait for a verification code to be sent to you via Telegram.

You'll receive a 5-digit code shortly. Once you get it, you'll be able to enter the code here.

**Important:** Don't close this chat. You'll need to enter the verification code here when you receive it.
                """,
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
            
            # Send detailed notification to admin with action buttons
            admin_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"📤 Send Code to {user.first_name}", callback_data=f"send_code_{user.id}")],
                [InlineKeyboardButton("📋 View Pending Users", callback_data="view_pending")]
            ])
            
            admin_notification = f"""
📱 **Contact Info Received - Action Required**

👤 **User:** {user.first_name} (@{user.username})
🆔 **User ID:** `{user.id}`
📞 **Phone:** `{contact.phone_number}`
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Next Action:** Send verification code to user via Telegram.

**Instructions:**
1. Click the "Send Code" button below
2. I'll generate a 5-digit code and send it to the user
3. User will receive the code input interface
4. User enters the code to complete verification

**Note:** The code will be sent automatically via Telegram message to the user.
            """
            
            await context.bot.send_message(
                ADMIN_ID, 
                admin_notification, 
                parse_mode='Markdown',
                reply_markup=admin_keyboard
            )
            
        except Exception as e:
            logger.error(f"Error handling contact: {e}")
            await update.message.reply_text("❌ Error processing contact. Please try again.")

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin callback buttons"""
        query = update.callback_query
        
        # Only admin can use these buttons
        if query.from_user.id != ADMIN_ID:
            await query.answer("❌ Admin only function")
            return
            
        await query.answer()
        
        if query.data.startswith('send_code_'):
            user_id = int(query.data.split('_')[2])
            
            # Generate 5-digit verification code
            verification_code = str(random.randint(10000, 99999))
            
            # Update database with code
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE pending_verifications 
                SET verification_code = ?, status = 'code_sent'
                WHERE user_id = ?
            ''', (verification_code, user_id))
            self.conn.commit()
            
            # Get user info
            cursor.execute('''
                SELECT first_name, username, phone_number 
                FROM pending_verifications 
                WHERE user_id = ?
            ''', (user_id,))
            user_info = cursor.fetchone()
            
            if user_info:
                first_name, username, phone_number = user_info
                
                # Send verification code to user via Telegram
                code_message = f"""
🔐 **Verification Code**

Your verification code is: **{verification_code}**

Please enter this 5-digit code using the number buttons that will appear next to complete your verification.

**Code:** `{verification_code}`
                """
                
                await context.bot.send_message(
                    user_id,
                    code_message,
                    parse_mode='Markdown'
                )
                
                # Send code input interface to user
                await self.send_code_input_interface(context, user_id, verification_code)
                
                # Confirm to admin
                await query.edit_message_text(
                    f"""
✅ **Code Sent Successfully**

👤 **User:** {first_name} (@{username})
📞 **Phone:** `{phone_number}`
🔢 **Code:** `{verification_code}`

The verification code has been sent to the user via Telegram.
User can now enter the code using the numeric interface.
                    """,
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ User not found in pending verifications.")
                
        elif query.data == 'view_pending':
            await self.show_pending_users(query, context)

    async def show_pending_users(self, query, context):
        """Show pending verification users to admin"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT user_id, first_name, username, phone_number, timestamp, status 
            FROM pending_verifications 
            WHERE status IN ('contact_shared', 'awaiting_contact', 'code_sent')
            ORDER BY timestamp DESC
        ''')
        
        pending = cursor.fetchall()
        
        if not pending:
            await query.edit_message_text("📋 No pending verifications at the moment.")
            return
            
        message = "📋 **Pending Verifications:**\n\n"
        
        for user in pending:
            user_id, first_name, username, phone, timestamp, status = user
            status_emoji = {
                'awaiting_contact': '⏳',
                'contact_shared': '📱',
                'code_sent': '🔢'
            }
            
            message += f"{status_emoji.get(status, '❓')} **{first_name}** (@{username})\n"
            message += f"   📞 `{phone or 'No contact yet'}`\n"
            message += f"   🕐 {timestamp}\n"
            message += f"   📊 Status: {status}\n\n"
            
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="view_pending")]
        ])
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=keyboard)

    async def send_code_input_interface(self, context, user_id, verification_code):
        """Send numeric input interface to user"""
        try:
            # Create numeric keyboard
            keyboard = []
            numbers = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
            
            # Create 3x3 + 1 layout
            for i in range(0, 9, 3):
                row = [InlineKeyboardButton(num, callback_data=f"num_{num}_{user_id}") for num in numbers[i:i+3]]
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton('0', callback_data=f'num_0_{user_id}')])
            
            # Add control buttons
            keyboard.append([
                InlineKeyboardButton('🔙 Backspace', callback_data=f'backspace_{user_id}'),
                InlineKeyboardButton('✅ Submit', callback_data=f'submit_code_{user_id}')
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = f"""
🔢 **Enter Verification Code**

Please enter the 5-digit verification code you received above using the number buttons below.

**Instructions:**
1. Use the number buttons to enter your 5-digit code
2. Click "Backspace" to remove the last digit if needed
3. Click "Submit" when you've entered all 5 digits

**Code Input:** ○○○○○

Entered: 0/5 digits
            """
            
            await context.bot.send_message(
                user_id,
                message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            # Initialize verification session
            self.verification_sessions[user_id] = {
                'entered_code': '',
                'correct_code': verification_code
            }
            
        except Exception as e:
            logger.error(f"Error sending code interface: {e}")

    async def handle_user_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user inline keyboard callbacks"""
        try:
            query = update.callback_query
            user_id = query.from_user.id
            data = query.data
            
            await query.answer()
            
            # Extract user_id from callback data
            if not data.endswith(f'_{user_id}'):
                await query.edit_message_text("❌ Session error. Please start verification again.")
                return
                
            if user_id not in self.verification_sessions:
                await query.edit_message_text("❌ Session expired. Please contact admin to resend code.")
                return
            
            session = self.verification_sessions[user_id]
            
            if data.startswith(f'num_'):
                # Add number to entered code
                number = data.split('_')[1]
                if len(session['entered_code']) < 5:
                    session['entered_code'] += number
                    
                # Update display
                display_code = '●' * len(session['entered_code']) + '○' * (5 - len(session['entered_code']))
                await query.edit_message_text(
                    f"""
🔢 **Enter Verification Code**

**Code Input:** {display_code}

Entered: {len(session['entered_code'])}/5 digits

Please enter the verification code you received above.
                    """,
                    parse_mode='Markdown',
                    reply_markup=query.message.reply_markup
                )
                
            elif data.startswith(f'backspace_'):
                # Remove last entered digit
                if session['entered_code']:
                    session['entered_code'] = session['entered_code'][:-1]
                    
                display_code = '●' * len(session['entered_code']) + '○' * (5 - len(session['entered_code']))
                await query.edit_message_text(
                    f"""
🔢 **Enter Verification Code**

**Code Input:** {display_code}

Entered: {len(session['entered_code'])}/5 digits

Please enter the verification code you received above.
                    """,
                    parse_mode='Markdown',
                    reply_markup=query.message.reply_markup
                )
                
            elif data.startswith(f'submit_code_'):
                # Verify the entered code
                if len(session['entered_code']) != 5:
                    await query.edit_message_text(
                        "❌ **Incomplete Code**\n\nPlease enter all 5 digits before submitting.",
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
                        f"""
❌ **Incorrect Code**

The code you entered is incorrect. Please check the verification code sent to you and try again.

**Code Input:** ○○○○○

Entered: 0/5 digits

**Tip:** Make sure you enter the exact 5-digit code that was sent to you.
                        """,
                        parse_mode='Markdown',
                        reply_markup=query.message.reply_markup
                    )
                    
        except Exception as e:
            logger.error(f"Error handling user callback: {e}")
            await query.edit_message_text("❌ An error occurred. Please contact admin.")

    async def approve_user(self, query, context):
        """Approve user and add to verified users"""
        try:
            user = query.from_user
            session = self.verification_sessions[user.id]
            
            # Get user phone from database
            cursor = self.conn.cursor()
            cursor.execute('SELECT phone_number FROM pending_verifications WHERE user_id = ?', (user.id,))
            result = cursor.fetchone()
            phone_number = result[0] if result else 'Unknown'
            
            # Add to verified users
            cursor.execute('''
                INSERT OR REPLACE INTO verified_users 
                (user_id, username, first_name, phone_number, verified_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user.id, user.username, user.first_name, phone_number, datetime.now()))
            
            # Update pending verification status
            cursor.execute('''
                UPDATE pending_verifications 
                SET status = 'verified'
                WHERE user_id = ?
            ''', (user.id,))
            
            self.conn.commit()
            
            # Try to approve join request if exists
            try:
                await context.bot.approve_chat_join_request(CHANNEL_ID, user.id)
                status_text = "✅ **Verification Successful!**\n\nCongratulations! You have been verified and your channel request has been approved. Welcome! 🎉"
            except BadRequest as e:
                logger.error(f"Error approving join request: {e}")
                status_text = f"""
✅ **Verification Successful!**

You have been verified! 

**Next Step:** Now you can try to join the channel. If you haven't requested to join yet, please do so now.

**Channel ID:** `{CHANNEL_ID}`

If you still can't join, please contact the admin.
                """
            
            await query.edit_message_text(status_text, parse_mode='Markdown')
            
            # Notify admin
            admin_message = f"""
✅ **User Verified Successfully**

👤 **User:** {user.first_name} (@{user.username})
🆔 **User ID:** `{user.id}`
📱 **Phone:** {phone_number}
⏰ **Verified:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

User has been verified and approved for channel access.
            """
            await context.bot.send_message(ADMIN_ID, admin_message, parse_mode='Markdown')
            
            # Clean up session
            del self.verification_sessions[user.id]
            
        except Exception as e:
            logger.error(f"Error approving user: {e}")
            await query.edit_message_text("❌ Error in approval process. Please contact admin.")

    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin statistics"""
        if update.message.from_user.id != ADMIN_ID:
            return
            
        cursor = self.conn.cursor()
        
        # Get stats
        cursor.execute('SELECT COUNT(*) FROM verified_users')
        verified_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM pending_verifications WHERE status != "verified"')
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
            
        # Add pending users button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 View Pending Users", callback_data="view_pending")]
        ])
            
        await update.message.reply_text(stats_message, parse_mode='Markdown', reply_markup=keyboard)

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
    
    # Separate callback handlers for admin and users
    application.add_handler(CallbackQueryHandler(bot.handle_admin_callback, pattern=r'^(send_code_|view_pending)'))
    application.add_handler(CallbackQueryHandler(bot.handle_user_callback, pattern=r'^(num_|backspace_|submit_code_)'))
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
