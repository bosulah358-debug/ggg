import logging
import os 
import re 
from datetime import datetime, timedelta
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
from telegram.error import TelegramError

from database import Database # تأكد أن هذا الملف موجود وصحيح

# -------------------- Global Configuration --------------------
# يجب تعيين BOT_TOKEN و WEBHOOK_URL في Render Dashboard
BOT_TOKEN = os.environ.get("8458158034:AAGbNwJH5Sn2FQqnkxIkZTvLWjglGUfcBaU") 
PORT = int(os.environ.get('PORT', 8080))
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://your-app-name.onrender.com')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set. Please set it on Render.")
# --------------------------------------------------------------

# -------------------- Global States and Variables --------------------

# تعريف حالات المحادثة
WAITING_FOR_KEYWORD, WAITING_FOR_REPLY = range(2)
WAITING_FOR_GLOBAL_KEYWORD, WAITING_FOR_GLOBAL_REPLY = range(2, 4)
WAITING_FOR_CUSTOM_WELCOME = 4 
WAITING_FOR_FORBIDDEN_WORD = 5 

OWNER_ID = None
OWNER_USERNAME = "@h_7_m" # يستخدم لـ is_admin

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()

# -------------------- الدوال الأساسية والتحقق --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("أضفني لمجموعتك", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    total_users = db.get_total_users()
    
    welcome_message = (
        "• أهلاً بك عزيزي انا بوت اسمي ديل\n"
        # ... (باقي الرسالة)
        f"• مطور البوت ↤︎ {OWNER_USERNAME}"
    )
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    if not update.effective_chat: return False
    chat_id = update.effective_chat.id
    user_id = user_id or update.effective_user.id
    
    # Check custom ranks
    if db.is_owner(chat_id, user_id) or db.is_admin(chat_id, user_id) or db.is_vip(chat_id, user_id):
        return True
    
    # Check Telegram ranks
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except:
        return False
        
# -------------------- دوال الأقفال والتحكم الجديدة --------------------

async def toggle_lock(update: Update, context: ContextTypes.DEFAULT_TYPE, lock_type: str, action: bool):
    """دالة مساعدة لتبديل حالة أي قفل في المجموعة."""
    if update.effective_chat.type == 'private' or not await is_admin(update, context):
        await update.message.reply_text("هذا الأمر للمشرفين فقط")
        return

    chat_id = update.effective_chat.id
    db.set_lock_status(chat_id, lock_type, action) 
    status = "تم قفل" if action else "تم فتح"
    
    lock_name_ar = {
        'links': 'الروابط', 'photos': 'الصور', 'gifs': 'المتحركات',  
        'stickers': 'الملصقات', 'forward': 'التوجيه', 'antiflood_new': 'كتم الأعضاء الجدد'
    }.get(lock_type, lock_type)
    
    await update.message.reply_text(f"{status} **{lock_name_ar}** بنجاح.", parse_mode='Markdown')

async def lock_links(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'links', True)
async def unlock_links(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'links', False)
async def lock_photos(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'photos', True)
async def unlock_photos(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'photos', False)
async def lock_gifs(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'gifs', True)
async def unlock_gifs(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'gifs', False)
async def lock_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'stickers', True)
async def unlock_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'stickers', False)
async def lock_forward(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'forward', True)
async def unlock_forward(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'forward', False)
async def enable_new_user_mute(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'antiflood_new', True)
async def disable_new_user_mute(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_lock(update, context, 'antiflood_new', False)


# -------------------- رسائل المغادرة المخصصة (تمت الإضافة) --------------------

async def enable_leave_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not await is_admin(update, context): return
    db.set_leave_message_status(update.effective_chat.id, True) 
    await update.message.reply_text(f"تم تفعيل رسالة مغادرة الأعضاء.")

async def disable_leave_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not await is_admin(update, context): return
    db.set_leave_message_status(update.effective_chat.id, False) 
    await update.message.reply_text(f"تم تعطيل رسالة مغادرة الأعضاء.")

async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not update.message.left_chat_member: return
    
    chat_id = update.effective_chat.id
    if db.is_leave_message_enabled(chat_id): 
        member_name = update.message.left_chat_member.first_name
        await context.bot.send_message(
            chat_id,
            f"غادرنا للتو العضو [{member_name}](tg://user?id={update.message.left_chat_member.id}) 💔.",
            parse_mode='Markdown'
        )

# -------------------- دوال نظام الردود والمحادثة (تمت الإضافة) --------------------

async def add_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        await update.message.reply_text("هذا الأمر يعمل فقط في المجموعات.")
        return ConversationHandler.END
    
    if not await is_admin(update, context):
        await update.message.reply_text("هذا الأمر للمشرفين فقط")
        return ConversationHandler.END
    
    await update.message.reply_text("حسناً الآن ارسل الكلمة التي تريدها للرد.")
    return WAITING_FOR_KEYWORD

async def cancel_add_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("تم الغاء اضافة الرد")
    return ConversationHandler.END

async def add_global_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME.lstrip('@'): 
        await update.message.reply_text("هذا الأمر للمطور فقط")
        return ConversationHandler.END
    
    await update.message.reply_text("حسنًا، أرسل الكلمة التي تريد أن يرد عليها.")
    return WAITING_FOR_GLOBAL_KEYWORD

async def receive_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['keyword'] = update.message.text.strip()
    await update.message.reply_text("حسناً، الآن ارسل الرد الذي تريده لهذه الكلمة.")
    return WAITING_FOR_REPLY

async def receive_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = context.user_data.get('keyword')
    # يجب إضافة منطق حفظ الرد هنا في database.py
    await update.message.reply_text(f"تم حفظ الرد المحلي للكلمة: **{keyword}** بنجاح.", parse_mode='Markdown')
    context.user_data.clear()
    return ConversationHandler.END

async def receive_global_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['global_keyword'] = update.message.text.strip()
    await update.message.reply_text("حسناً، الآن ارسل الرد العام الذي تريده.")
    return WAITING_FOR_GLOBAL_REPLY

async def receive_global_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = context.user_data.get('global_keyword')
    # يجب إضافة منطق حفظ الرد العام هنا في database.py
    await update.message.reply_text(f"تم حفظ الرد العام للكلمة: **{keyword}** بنجاح.", parse_mode='Markdown')
    context.user_data.clear()
    return ConversationHandler.END

async def add_forbidden_word_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not await is_admin(update, context):
        await update.message.reply_text("هذا الأمر للمشرفين فقط")
        return ConversationHandler.END
    await update.message.reply_text("حسناً، الآن أرسل الكلمة التي تريد إضافتها للقائمة الممنوعة.")
    return WAITING_FOR_FORBIDDEN_WORD

async def receive_forbidden_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = update.message.text.strip()
    chat_id = update.effective_chat.id
    db.add_forbidden_word(chat_id, word) 
    await update.message.reply_text(f"تمت إضافة الكلمة **{word}** إلى قائمة الكلمات الممنوعة.", parse_mode='Markdown')
    return ConversationHandler.END

async def clear_forbidden_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not await is_admin(update, context):
        await update.message.reply_text("هذا الأمر للمشرفين فقط")
        return
    db.clear_forbidden_words(update.effective_chat.id) 
    await update.message.reply_text("تم مسح قائمة الكلمات الممنوعة بالكامل.")


# -------------------- الدوال المتبقية (يجب أن تكون موجودة في الكود الأصلي) --------------------

# دوال يجب أن تكون معرفة لديك لتجنب NameError
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def check_bot_member(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def check_spam(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def reply_to_salam(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def check_global_replies(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def check_custom_replies(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def check_group_locked(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def track_messages(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def warn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def commands_callback(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def check_content_locks(update: Update, context: ContextTypes.DEFAULT_TYPE): pass
async def handle_arabic_commands(update: Update, context: ContextTypes.DEFAULT_TYPE): pass

# ... (كل دوال الأوامر الأخرى مثل ban_user, kick_user, إلخ)

# -------------------- دالة main (تشغيل الـ Webhook) --------------------

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation Handlers (تم تصحيح states و fallbacks هنا)
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^اضف رد$'), add_reply_start)],
        states={
            WAITING_FOR_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_keyword)],
            WAITING_FOR_REPLY: [MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION | 
                 filters.VOICE | filters.AUDIO | filters.Document.ALL) & ~filters.COMMAND,
                receive_reply
            )]
        },
        fallbacks=[MessageHandler(filters.Regex('^الغاء$'), cancel_add_reply)],
        allow_reentry=True
    )
    
    global_reply_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^اضف رد عام$'), add_global_reply_start)],
        states={
            WAITING_FOR_GLOBAL_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_global_keyword)],
            WAITING_FOR_GLOBAL_REPLY: [MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION | 
                 filters.VOICE | filters.AUDIO | filters.Document.ALL) & ~filters.COMMAND,
                receive_global_reply
            )]
        },
        fallbacks=[MessageHandler(filters.Regex('^الغاء$'), cancel_add_reply)],
        allow_reentry=True
    )

    forbidden_word_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^اضف كلمة ممنوعة$'), add_forbidden_word_start)],
        states={
            WAITING_FOR_FORBIDDEN_WORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_forbidden_word)]
        },
        fallbacks=[MessageHandler(filters.Regex('^الغاء$'), cancel_add_reply)],
        allow_reentry=True
    )
    
    application.add_handler(conv_handler)
    application.add_handler(global_reply_handler)
    application.add_handler(forbidden_word_handler)
    
    # 1. Handlers for Locks & Updates (Group 0 - High Priority)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, check_content_locks), group=0)
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_left_member), group=0)
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member), group=0)
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, check_bot_member), group=0)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_spam), group=0)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_to_salam), group=0)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_global_replies), group=0)

    # 2. Handlers for Arabic Commands and Group Locks (Group 1 & 2)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_custom_replies), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_group_locked), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_arabic_commands), group=2)
    
    # 3. Tracking (Group 3 - Low Priority)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_messages), group=3)
    
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(warn_callback, pattern="^warn_"))
    application.add_handler(CallbackQueryHandler(commands_callback, pattern="^cmd_"))
    
    # 4. RUN WEBHOOK
    logger.info(f"Starting webhook on port {PORT} at URL path '/'")
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="",
        webhook_url=f"{WEBHOOK_URL}"
    )

if __name__ == '__main__':
    main()
