import logging
import os # NEW: Added for reading environment variables
import re 
from datetime import datetime, timedelta
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
from telegram.error import TelegramError

from database import Database # MAKE SURE THIS FILE EXISTS AND SUPPORTS NEW LOCKS

# --- Global Configuration (Read from Environment) ---
# ستقوم Render بتعيين هذه المتغيرات تلقائياً
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # <--- تم تغيير القيمة إلى "BOT_TOKEN"
PORT = int(os.environ.get('PORT', 8080))
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://your-app-name.onrender.com')
if not BOT_TOKEN:
    # هذا الخطأ سيوقف التشغيل إذا لم يتم تعيين التوكن في Render
    raise ValueError("BOT_TOKEN environment variable not set. Please set it on Render.")
# ----------------------------------------------------

# ... (ضع هذا الكود في ملف main.py قبل دالة main())

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

# تأكد أيضًا من وجود هذه الدوال للردود العامة إذا كنت تستخدمها
async def add_global_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # منطق التحقق من المطور
    if update.effective_user.username != OWNER_USERNAME.lstrip('@'): 
        await update.message.reply_text("هذا الأمر للمطور فقط")
        return ConversationHandler.END
    
    await update.message.reply_text("حسنًا، أرسل الكلمة التي تريد أن يرد عليها.")
    return WAITING_FOR_GLOBAL_KEYWORD

# ... (تأكد من وجود باقي دوال المحادثة مثل receive_keyword، receive_reply، إلخ.)
# Define conversation states globally (Updated to include new states)
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

# -------------------- الدوال الأساسية والدوال القديمة --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("أضفني لمجموعتك", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    total_users = db.get_total_users()
    
    welcome_message = (
        "• أهلاً بك عزيزي انا بوت اسمي انجل\n"
        "• اختصاص البوت حماية المجموعات\n"
        "• اضف البوت الى مجموعتك .\n"
        "• ارفعه ادمن مشرف\n"
        "• ارفعه مشرف وارسل تفعيل ليتم تفعيل المجموعة .\n"
        f"• عدد المستخدمين: {total_users}\n"
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

# (بقية دوال الأوامر القديمة مثل ban_user, restrict_user, warn_user, commands_list, clear_messages, إلخ.)
# (تم حذفها من هذا الرد للإيجاز، لكنها موجودة في الكود المدمج لديك)
# --------------------------------------------------------------------------------------------------

# -------------------- دوال الأقفال والتحكم الجديدة --------------------

async def toggle_lock(update: Update, context: ContextTypes.DEFAULT_TYPE, lock_type: str, action: bool):
    """دالة مساعدة لتبديل حالة أي قفل في المجموعة."""
    if update.effective_chat.type == 'private' or not await is_admin(update, context):
        await update.message.reply_text("هذا الأمر للمشرفين فقط")
        return

    chat_id = update.effective_chat.id
    db.set_lock_status(chat_id, lock_type, action) # يجب تنفيذ هذه الدالة في database.py
    status = "تم قفل" if action else "تم فتح"
    
    lock_name_ar = {
        'links': 'الروابط', 'photos': 'الصور', 'gifs': 'المتحركات', 
        'stickers': 'الملصقات', 'forward': 'التوجيه', 'antiflood_new': 'كتم الأعضاء الجدد'
    }.get(lock_type, lock_type)
    
    await update.message.reply_text(f"{status} **{lock_name_ar}** بنجاح.", parse_mode='Markdown')

# دوال الأوامر الجديدة
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

# -------------------- الكلمات الممنوعة (Conversation Handlers) --------------------

async def add_forbidden_word_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not await is_admin(update, context):
        await update.message.reply_text("هذا الأمر للمشرفين فقط")
        return ConversationHandler.END
    await update.message.reply_text("حسناً، الآن أرسل الكلمة التي تريد إضافتها للقائمة الممنوعة.")
    return WAITING_FOR_FORBIDDEN_WORD

async def receive_forbidden_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = update.message.text.strip()
    chat_id = update.effective_chat.id
    db.add_forbidden_word(chat_id, word) # يجب تنفيذ هذه الدالة في database.py
    await update.message.reply_text(f"تمت إضافة الكلمة **{word}** إلى قائمة الكلمات الممنوعة.", parse_mode='Markdown')
    return ConversationHandler.END

async def clear_forbidden_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not await is_admin(update, context):
        await update.message.reply_text("هذا الأمر للمشرفين فقط")
        return
    db.clear_forbidden_words(update.effective_chat.id) # يجب تنفيذ هذه الدالة في database.py
    await update.message.reply_text("تم مسح قائمة الكلمات الممنوعة بالكامل.")

# -------------------- رسائل المغادرة المخصصة --------------------

async def enable_leave_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not await is_admin(update, context): return
    db.set_leave_message_status(update.effective_chat.id, True) # يجب تنفيذ هذه الدالة
    await update.message.reply_text(f"تم تفعيل رسالة مغادرة الأعضاء.")

async def disable_leave_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not await is_admin(update, context): return
    db.set_leave_message_status(update.effective_chat.id, False) # يجب تنفيذ هذه الدالة
    await update.message.reply_text(f"تم تعطيل رسالة مغادرة الأعضاء.")

async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not update.message.left_chat_member: return
    
    chat_id = update.effective_chat.id
    if db.is_leave_message_enabled(chat_id): # يجب تنفيذ هذه الدالة
        member_name = update.message.left_chat_member.first_name
        await context.bot.send_message(
            chat_id,
            f"غادرنا للتو العضو [{member_name}](tg://user?id={update.message.left_chat_member.id}) 💔.",
            parse_mode='Markdown'
        )

# -------------------- فحص المحتوى والأقفال (CORE LOGIC) --------------------

async def check_content_locks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private' or not update.message: return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if await is_admin(update, context, user_id): return

    settings = db.get_group_settings(chat_id) # يجب أن ترجع كل الإعدادات
    message_deleted = False

    try:
        # فحص التوجيه
        if settings.get('lock_forward') and update.message.forward_date:
            await update.message.delete()
            message_deleted = True
        
        # فحص الملصقات
        if not message_deleted and settings.get('lock_stickers') and update.message.sticker:
            await update.message.delete()
            message_deleted = True

        # فحص الروابط والكلمات الممنوعة
        if not message_deleted and update.message.text:
            text = update.message.text
            
            # فحص الروابط
            if settings.get('lock_links') and re.search(r'https?://\S+|www\.\S+|\w+\.t\.me', text):
                await update.message.delete()
                await context.bot.send_message(chat_id, f"الروابط مقفلة.", reply_to_message_id=update.message.message_id)
                message_deleted = True
                
            # فحص الكلمات الممنوعة
            if not message_deleted and settings.get('forbidden_words'):
                for word in settings['forbidden_words']:
                    # البحث عن الكلمة ككلمة كاملة (\b)
                    if re.search(r'\b' + re.escape(word) + r'\b', text, re.IGNORECASE):
                        await update.message.delete()
                        await context.bot.send_message(chat_id, f"هذه الكلمة ممنوعة.", reply_to_message_id=update.message.message_id)
                        message_deleted = True
                        break

    except TelegramError as e:
        logger.warning(f"Failed to delete message: {e}")

# -------------------- دالة معالجة الأوامر العربية (محدثة) --------------------

async def handle_arabic_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    
    # قاموس يدمج جميع الأوامر القديمة والجديدة
    command_handlers = {
        'حظر': ban_user, 'تقييد': restrict_user, 'طرد': kick_user, 'كتم': mute_user, 'انذار': warn_user, 
        'فك الحظر': unban_user, 'الغاء الكتم': unmute_user, 'فك التقييد': unrestrict_user, 'رفع مميز': promote_vip, 
        'رفع مدير': promote_admin, 'تنزيل الكل': demote_user, 'كشف': check_user, 'عرض التوب': top_users, 
        'الاوامر': commands_list, 'مسح الكل': clear_all, 'مسح المحظورين': clear_banned, 'مسح المكتومين': clear_muted, 
        'مسح بالرد': delete_message, 'تفعيل الترحيب': enable_welcome, 'تعطيل الترحيب': disable_welcome, 'تفعيل': enable_welcome,
        'الإدمنية': show_admins, 'قفل القروب': lock_group, 'فتح القروب': unlock_group, 'احصائيات البوت': bot_stats,
        'إيقاف البوت': disable_bot, 'تشغيل البوت': enable_bot, 'انجل': angel_command, 'انذاراتي': get_warnings,
        'اخر رسايلي': get_my_messages,
        
        # الأوامر الجديدة
        'قفل الروابط': lock_links, 'فتح الروابط': unlock_links,
        'قفل الصور': lock_photos, 'فتح الصور': unlock_photos,
        'قفل المتحركات': lock_gifs, 'فتح المتحركات': unlock_gifs,
        'قفل الملصقات': lock_stickers, 'فتح الملصقات': unlock_stickers,
        'قفل التوجيه': lock_forward, 'فتح التوجيه': unlock_forward,
        'تفعيل كتم الجدد': enable_new_user_mute, 'تعطيل كتم الجدد': disable_new_user_mute,
        'تفعيل رسالة المغادرة': enable_leave_message, 'تعطيل رسالة المغادرة': disable_leave_message,
        'مسح الكلمات الممنوعة': clear_forbidden_words,
    }
    
    # تنفيذ الأوامر المباشرة
    if text in command_handlers:
        await command_handlers[text](update, context)
        return

    # تنفيذ الأوامر التي تحتاج إلى نص إضافي (كتم مؤقت، مسح بعدد، إضافة كلمات)
    if text.startswith('كتم ') and (text.endswith('د') or text.endswith('س')):
        context.args = [text[4:]]
        await temp_mute_user(update, context)
        return
    
    if text.startswith('مسح ') and text[4:].isdigit():
        context.args = [text[4:]]
        await clear_messages(update, context)
        return

    # الأوامر التي تبدأ بـ 'اضف كلمة ممنوعة' يتم التعامل معها الآن عبر Conversation Handler

# -------------------- دالة main (تشغيل الـ Webhook) --------------------

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers (Conversation Handlers)
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^اضف رد$'), add_reply_start)],
        # ... (بقية الحالات)
        allow_reentry=True
    )
    
    global_reply_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^اضف رد عام$'), add_global_reply_start)],
        # ... (بقية الحالات)
        allow_reentry=True
    )

    # NEW: Conversation Handler for Forbidden Words
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
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, check_content_locks), group=0) # فحص الأقفال
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_left_member), group=0) # رسالة المغادرة
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
        listen="0.0.0.0", # ضروري لتشغيل Render
        port=PORT,
        url_path="",
        webhook_url=f"{WEBHOOK_URL}"
    )

if __name__ == '__main__':
    main()
