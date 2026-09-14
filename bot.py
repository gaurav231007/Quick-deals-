import os
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from supabase import create_client, Client

TOKEN = os.getenv("TOKEN")
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID")
ADMIN_USER_ID = int(ADMIN_USER_ID_STR) if ADMIN_USER_ID_STR else None
UPI_ID = os.getenv("UPI_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SECRET_KEY")
STORAGE_CHANNEL_ID = os.getenv("STORAGE_CHANNEL_ID")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

VIDEOS_FILE = "videos.txt"


def load_videos_from_file():
    if not os.path.exists(VIDEOS_FILE):
        return []
    try:
        with open(VIDEOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_videos_to_file(videos):
    try:
        with open(VIDEOS_FILE, "w", encoding="utf-8") as f:
            json.dump(videos, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Error saving videos file: {e}")


def db_get_channels():
    if not supabase:
        return {}
    try:
        res = supabase.table("channels").select("*").execute()
        channels = {}
        for row in res.data:
            channels[str(row["channel_id"])] = {
                "name": row["name"],
                "price": row["price"],
                "days": row["days"]
            }
        return channels
    except Exception as e:
        logging.error(f"DB Get Channels Error: {e}")
        return {}


def db_save_channel(channel_id, name, price, days):
    if not supabase:
        return
    try:
        supabase.table("channels").upsert({
            "channel_id": str(channel_id),
            "name": str(name),
            "price": int(price),
            "days": int(days)
        }).execute()
    except Exception as e:
        logging.error(f"DB Save Channel Error: {e}")


def db_get_subscription(user_id, channel_id):
    if not supabase:
        return None
    try:
        res = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).eq("channel_id", str(channel_id)).execute()
        if res.data:
            row = res.data[0]
            expiry = datetime.fromisoformat(row["expiry"])
            start_date = datetime.fromisoformat(row["start_date"])
            return {"expiry": expiry, "start_date": start_date, "price_paid": row["price_paid"]}
    except Exception as e:
        logging.error(f"DB Fetch Error: {e}")
    return None


def db_save_subscription(user_id, channel_id, expiry, start_date, price_paid):
    if not supabase:
        return
    try:
        supabase.table("subscriptions").upsert({
            "user_id": int(user_id),
            "channel_id": str(channel_id),
            "expiry": expiry.isoformat(),
            "start_date": start_date.isoformat(),
            "price_paid": int(price_paid)
        }).execute()
    except Exception as e:
        logging.error(f"DB Save Error: {e}")


def db_get_all_active_subscriptions(user_id):
    if not supabase:
        return {}
    try:
        now = datetime.now()
        res = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).execute()
        active = {}
        for row in res.data:
            expiry = datetime.fromisoformat(row["expiry"])
            if expiry > now:
                active[row["channel_id"]] = {
                    "expiry": expiry,
                    "start_date": datetime.fromisoformat(row["start_date"]),
                    "price_paid": row["price_paid"]
                }
        return active
    except Exception as e:
        logging.error(f"DB Active Subs Error: {e}")
        return {}


def db_get_all_subscriptions():
    if not supabase:
        return []
    try:
        res = supabase.table("subscriptions").select("*").execute()
        return res.data
    except Exception as e:
        logging.error(f"DB Get All Subs Error: {e}")
        return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    managed_channels = db_get_channels()
    
    if ADMIN_USER_ID and user_id == ADMIN_USER_ID:
        text = "👑 **Admin Panel / Status:**\nAapke paas Admin access hai."
        keyboard = [
            [InlineKeyboardButton("🎬 Get Today's Video", callback_data="get_videos_info")],
            [InlineKeyboardButton("⚙️ Admin Control Panel", callback_data="admin_panel")]
        ]
    else:
        active_subs = db_get_all_active_subscriptions(user_id)
        keyboard = []
        
        if active_subs:
            text = "📱 **Aapka Active Subscription Status:**\n\n"
            for ch_id, info in active_subs.items():
                ch_name = managed_channels.get(ch_id, {}).get("name", "Channel")
                text += f"📦 **{ch_name}**\n⏳ Valid Until: `{info['expiry'].strftime('%Y-%m-%d %H:%M')}`\n\n"
            
            keyboard.append([InlineKeyboardButton("🚀 Upgrade Your Plan", callback_data="show_plans")])
        else:
            name = update.effective_user.first_name if update.effective_user else "User"
            text = (
                f"👋 Hello {name}!\n\n"
                "❌ **Aapka koi active subscription nahi hai.**\n"
                "Daily videos aur access ke liye niche diye gaye plan par click karein:"
            )
            for ch_id, details in managed_channels.items():
                keyboard.append([
                    InlineKeyboardButton(f"🚀 {details['name']} ({details['price']}₹ / {details['days']} Days)", callback_data=f"buy_{ch_id}")
                ])

        keyboard.append([InlineKeyboardButton("🎬 Get Today's Video", callback_data="get_videos_info")])
        keyboard.append([InlineKeyboardButton("💬 Contact Support / Help", callback_data="help_support")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if edit and update.callback_query:
        try:
            await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception:
            await update.callback_query.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown", protect_content=True)


async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
        active_subs = db_get_all_active_subscriptions(user_id)
        if not active_subs:
            await update.message.reply_text(
                "❌ **Aapne subscription nahi liya hai!**\n\nDaily videos access karne ke liye pehle /start dabakar plan buy karein.",
                parse_mode="Markdown",
                protect_content=True
            )
            return
        
    videos = load_videos_from_file()
    if not videos:
        await update.message.reply_text("📭 Filhal koi video available nahi hai.", protect_content=True)
        return

    vid = videos[-1]
    await update.message.reply_text("🎬 **Aapke liye Aaj ki Video:**", parse_mode="Markdown", protect_content=True)
    
    try:
        if vid["type"] == "video":
            await context.bot.send_video(chat_id=user_id, video=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)
        elif vid["type"] == "document":
            await context.bot.send_document(chat_id=user_id, document=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)
    except Exception as e:
        logging.error(f"Error sending video: {e}")


async def send_specific_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_USER_ID or update.effective_user.id != ADMIN_USER_ID:
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /sendvideo user_id video_index (jaise: /sendvideo 123456789 0)")
        return

    try:
        target_user_id = int(args[0])
        vid_index = int(args[1])
        videos = load_videos_from_file()
        
        if not videos or vid_index >= len(videos):
            await update.message.reply_text(f"❌ Invalid video index! Total videos stored: {len(videos)}")
            return
            
        vid = videos[vid_index]
        if vid["type"] == "video":
            await context.bot.send_video(chat_id=target_user_id, video=vid["file_id"], caption=vid.get("caption", "Specific Video from Admin"), protect_content=True)
        elif vid["type"] == "document":
            await context.bot.send_document(chat_id=target_user_id, document=vid["file_id"], caption=vid.get("caption", "Specific Video from Admin"), protect_content=True)
            
        await update.message.reply_text(f"✅ Successfully sent video index `{vid_index}` to user `{target_user_id}`!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error sending specific video: {e}")


async def handle_storage_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if not message:
        return
    
    if STORAGE_CHANNEL_ID and str(message.chat.id) == str(STORAGE_CHANNEL_ID):
        videos = load_videos_from_file()
        if message.video:
            videos.append({"type": "video", "file_id": message.video.file_id, "caption": message.caption or ""})
            save_videos_to_file(videos)
            logging.info(f"New video captured. Total stored: {len(videos)}")
        elif message.document:
            videos.append({"type": "document", "file_id": message.document.file_id, "caption": message.caption or ""})
            save_videos_to_file(videos)
            logging.info(f"New document captured. Total stored: {len(videos)}")


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle support messages from users safely"""
    if not update.effective_user or not update.message or not update.message.text:
        return
    
    user_id = update.effective_user.id
    
    if ADMIN_USER_ID and user_id == ADMIN_USER_ID:
        return
    
    if not context.user_data.get("waiting_for_support", False):
        return
    
    first_name = update.effective_user.first_name or "Unknown"
    username = update.effective_user.username or "No username"
    message_text = update.message.text
    
    if ADMIN_USER_ID:
        support_message = (
            f"New Support Message:\n\n"
            f"Name: {first_name}\n"
            f"Username: @{username}\n"
            f"User ID: {user_id}\n\n"
            f"Message:\n{message_text}"
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=support_message,
                protect_content=True
            )
        except Exception as e:
            logging.error(f"Error forwarding support message: {e}")
    
    await update.message.reply_text(
        "✅ Aapka message admin tak pahuncha diya gaya hai. Admin jald hi aapko reply dega.",
        protect_content=True
    )
    context.user_data["waiting_for_support"] = False


async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_USER_ID or update.effective_user.id != ADMIN_USER_ID:
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /reply user_id Aapka message yahan likhein")
        return

    try:
        target_user_id = int(args[0])
        reply_text = " ".join(args[1:])
        
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 **Admin Reply:**\n\n{reply_text}",
            parse_mode="Markdown",
            protect_content=True
        )
        await update.message.reply_text(f"✅ Reply successfully sent to user `{target_user_id}`!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error sending reply: {e}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    managed_channels = db_get_channels()

    if data == "show_plans":
        keyboard = []
        for ch_id, details in managed_channels.items():
            keyboard.append([
                InlineKeyboardButton(f"🚀 {details['name']} ({details['price']}₹ / {details['days']} Days)", callback_data=f"buy_{ch_id}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
        await query.edit_message_text(
            text="🚀 **Upgrade Your Plan:**\nSelect a plan below to extend your subscription:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "help_support":
        help_text = (
            "💬 **Customer Support & Help:**\n\n"
            "Agar aapko payment ya subscription mein koi bhi samasya aa rahi hai, toh aap seedha admin se sampark kar sakte hain.\n\n"
            "Niche likha gaya message type karein aur admin ko bhej denge:"
        )
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        await query.edit_message_text(text=help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        context.user_data["waiting_for_support"] = True

    elif data == "get_videos_info":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            active_subs = db_get_all_active_subscriptions(user_id)
            if not active_subs:
                await query.message.reply_text("❌ **Aapka koi active subscription nahi hai!** Kripya pehle plan buy karein.", parse_mode="Markdown")
                return

        videos = load_videos_from_file()
        if not videos:
            await query.message.reply_text("📭 Filhal koi video available nahi hai.", parse_mode="Markdown")
            return

        vid = videos[-1]
        await query.message.reply_text("🎬 **Aapke liye Aaj ki Video:**", parse_mode="Markdown", protect_content=True)
        
        try:
            if vid["type"] == "video":
                await context.bot.send_video(chat_id=user_id, video=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)
            elif vid["type"] == "document":
                await context.bot.send_document(chat_id=user_id, document=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)
        except Exception as e:
            logging.error(f"Error in button video send: {e}")
            await query.message.reply_text("❌ Video send karne mein error aaya.")

    elif data.startswith("buy_"):
        ch_id = data.replace("buy_", "")
        if ch_id not in managed_channels:
            await query.edit_message_text(text="Invalid channel selection.")
            return

        active_subs = db_get_all_active_subscriptions(user_id)
        if ch_id in active_subs:
            await query.answer("⚠️ Aapka yeh subscription pehle se active hai!", show_alert=True)
            return

        details = managed_channels[ch_id]
        
        if not UPI_ID:
            await query.edit_message_text(
                text="❌ **UPI Payment is not configured!**\n\nPlease contact admin for payment details.",
                parse_mode="Markdown"
            )
            logging.error("UPI_ID is not set in environment variables")
            return
        
        qr_caption = (
            f"🛍️ **Plan:** {details['name']} ({details['days']} Days)\n"
            f"💰 **Amount:** ₹{details['price']}\n\n"
            "1️⃣ Scan the QR code using any UPI app to pay.\n"
            "2️⃣ After payment, click the **'I Have Paid'** button below."
        )
        
        upi_string = f"upi://pay?pa={UPI_ID}&pn=Quick-Deals&am={details['price']}&tn=Subscription%20Payment"
        qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={quote(upi_string)}"

        keyboard = [
            [InlineKeyboardButton("✅ I Have Paid", callback_data=f"paid_{ch_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        
        try:
            await query.message.delete()
        except Exception:
            pass

        try:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=qr_image_url,
                caption=qr_caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                protect_content=True
            )
        except Exception as e:
            logging.error(f"Error generating QR code: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ **Error generating QR code!**\n\nPlease contact admin:\nUPI: `{UPI_ID}`\nAmount: ₹{details['price']}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
                protect_content=True
            )

    elif data.startswith("paid_"):
        ch_id = data.replace("paid_", "")
        details = managed_channels[ch_id]
        
        try:
            await query.edit_message_caption(
                caption="⏳ **Payment verification pending!**\nYour request has been sent to the admin.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        if ADMIN_USER_ID:
            admin_keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"app_{user_id}_{ch_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user_id}")
                ]
            ]
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"🔔 **New Payment Verification Request!**\n\n"
                     f"👤 **User ID:** `{user_id}`\n"
                     f"📦 **Channel ID:** `{ch_id}`\n"
                     f"💵 **Amount:** ₹{details['price']}",
                reply_markup=InlineKeyboardMarkup(admin_keyboard),
                parse_mode="Markdown",
                protect_content=True
            )

    elif data.startswith("app_"):
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        _, target_user_id, ch_id = data.split("_")
        target_user_id = int(target_user_id)
        
        details = managed_channels.get(ch_id, {"days": 30, "price": 0})
        days = details["days"]
        price = details["price"]
        now = datetime.now()
        
        existing = db_get_subscription(target_user_id, ch_id)
        if existing and existing["expiry"] > now:
            expiry = existing["expiry"] + timedelta(days=days)
        else:
            expiry = now + timedelta(days=days)

        db_save_subscription(target_user_id, ch_id, expiry, now, price)

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 **Payment Approved!** Aapka subscription active ho gaya hai (Valid until: {expiry.strftime('%Y-%m-%d %H:%M')}).\n\n🎬 **Aapki Aaj ki Video:**",
                parse_mode="Markdown",
                protect_content=True
            )
             videos = load_videos_from_file()
            if videos:
                vid = videos[-1]
                if vid["type"] == "video":
                    await context.bot.send_video(chat_id=target_user_id, video=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)
                elif vid["type"] == "document":
                    await context.bot.send_document(chat_id=target_user_id, video=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)

            await query.edit_message_text(text=f"✅ Approved and today's video sent to user `{target_user_id}`!", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(text=f"❌ Error: {e}")

    elif data.startswith("rej_"):
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        _, target_user_id = data.split("_")
        target_user_id = int(target_user_id)
        
        await context.bot.send_message(chat_id=target_user_id, text="❌ Your payment verification was rejected.", protect_content=True)
        await query.edit_message_text(text=f"❌ Rejected user `{target_user_id}`.")

    elif data == "admin_panel":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        keyboard = [
            [InlineKeyboardButton("📋 View Subscribers List", callback_data="admin_sub_list")],
            [InlineKeyboardButton("➕ Add/Update Channel Plan", callback_data="admin_channel_help")],
            [InlineKeyboardButton("🎁 Give Free Entry", callback_data="admin_free_help")],
            [InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            text="⚙️ **Admin Control Panel**\n\nManage channels, view subscribers, and grant access seamlessly.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "admin_sub_list":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        subs = db_get_all_subscriptions()
        text = "📋 **Subscribers List (Name & ID):**\n\n"
        
        if not subs:
            text += "No active subscribers found."
        else:
            now = datetime.now()
            for row in subs:
                uid = row["user_id"]
                status = "🟢 Active" if datetime.fromisoformat(row["expiry"]) > now else "🔴 Expired"
                
                try:
                    chat_info = await context.bot.get_chat(uid)
                    name = chat_info.first_name or "Unknown"
                except Exception:
                    name = "Unknown"
                
                text += f"👤 **Name:** {name}\n🆔 **ID:** `{uid}`\n📦 **Ch:** `{row['channel_id']}`\n📌 **Status:** {status}\n⏳ **Exp:** `{row['expiry'][:16]}`\n\n"

        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_channel_help":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        await query.edit_message_text(
            text="To add or update a channel plan price/days, send command in chat:\n`/addchannel -100xxxxxxxxxx Channel_Name Price Days`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "admin_free_help":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        await query.edit_message_text(
            text="To give free entry without payment, send command in chat:\n`/giveaccess user_id channel_id days`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif data == "main_menu":
        try:
            await query.message.delete()
        except Exception:
            pass
        await show_main_menu(update, context, edit=False)


async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_USER_ID or update.effective_user.id != ADMIN_USER_ID:
        return
    
    args = context.args
    if len(args) != 4:
        await update.message.reply_text("Usage: /addchannel -100xxxxxxxxxx Channel_Name Price Days")
        return

    ch_id, name, price, days = args[0], args[1], int(args[2]), int(args[3])
    db_save_channel(ch_id, name, price, days)
    await update.message.reply_text(f"✅ Channel Plan saved to Database!\nChannel: {name}\nPrice: ₹{price}\nValidity: {days} Days")


async def give_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_USER_ID or update.effective_user.id != ADMIN_USER_ID:
        return
    
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Usage: /giveaccess user_id channel_id days")
        return

    target_user_id, ch_id, days = int(args[0]), args[1], int(args[2])
    now = datetime.now()
    
    existing = db_get_subscription(target_user_id, ch_id)
    if existing and existing["expiry"] > now:
        expiry = existing["expiry"] + timedelta(days=days)
    else:
        expiry = now + timedelta(days=days)

    db_save_subscription(target_user_id, ch_id, expiry, now, 0)

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 **Access Granted by Admin!** Valid until {expiry.strftime('%Y-%m-%d %H:%M')}.\n\n🎬 **Aapki Aaj ki Video:**",
            protect_content=True
        )
        
        videos = load_videos_from_file()
        if videos:
            vid = videos[-1]
            if vid["type"] == "video":
                await context.bot.send_video(chat_id=target_user_id, video=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)
            elif vid["type"] == "document":
                await context.bot.send_document(chat_id=target_user_id, video=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)

        await update.message.reply_text(f"✅ Successfully granted access and sent today's video to user `{target_user_id}`!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error sending video: {e}")


def main():
    if not TOKEN:
        raise ValueError("No TOKEN found in environment variables!")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("sendvideo", send_specific_video_command))
    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(CommandHandler("addchannel", add_channel_command))
    app.add_handler(CommandHandler("giveaccess", give_access_command))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_storage_channel_post))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Complete Dynamic Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
    
