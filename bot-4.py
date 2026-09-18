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


def _safe_expiry(row):
    try:
        return datetime.fromisoformat(row["expiry"])
    except Exception:
        return None


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
        text = "Admin Panel / Status:\nAapke paas Admin access hai."
        keyboard = [
            [InlineKeyboardButton("Get Today's Video", callback_data="get_videos_info")],
            [InlineKeyboardButton("Admin Control Panel", callback_data="admin_panel")]
        ]
    else:
        active_subs = db_get_all_active_subscriptions(user_id)
        keyboard = []
        if active_subs:
            text = "Aapka Active Subscription Status:\n\n"
            for ch_id, info in active_subs.items():
                ch_name = managed_channels.get(ch_id, {}).get("name", "Channel")
                text += f"Package: {ch_name}\nValid Until: {info['expiry'].strftime('%Y-%m-%d %H:%M')}\n\n"
            keyboard.append([InlineKeyboardButton("Upgrade Your Plan", callback_data="show_plans")])
        else:
            name = update.effective_user.first_name if update.effective_user else "User"
            text = (
                f"Hello {name}!\n\n"
                "Aapka koi active subscription nahi hai.\n"
                "Daily videos aur access ke liye niche diye gaye plan par click karein:"
            )
            for ch_id, details in managed_channels.items():
                keyboard.append([
                    InlineKeyboardButton(f"{details['name']} ({details['price']} / {details['days']} Days)", callback_data=f"buy_{ch_id}")
                ])
        keyboard.append([InlineKeyboardButton("Get Today's Video", callback_data="get_videos_info")])
        keyboard.append([InlineKeyboardButton("Contact Support / Help", callback_data="help_support")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if edit and update.callback_query:
        try:
            await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
        except Exception:
            # Happens when the button is attached to a photo (e.g. the UPI QR) —
            # a photo message's caption can't become a plain text message, so
            # delete it and send the menu fresh instead of leaving it on screen.
            try:
                await update.callback_query.message.delete()
            except Exception:
                pass
            await update.callback_query.message.reply_text(text=text, reply_markup=reply_markup, protect_content=True)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup, protect_content=True)


async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
        active_subs = db_get_all_active_subscriptions(user_id)
        if not active_subs:
            await update.message.reply_text(
                "Aapne subscription nahi liya hai!\n\nDaily videos access karne ke liye pehle /start dabakar plan buy karein.",
                protect_content=True
            )
            return

    videos = load_videos_from_file()
    if not videos:
        await update.message.reply_text("Filhal koi video available nahi hai.", protect_content=True)
        return

    vid = videos[-1]
    await update.message.reply_text("Aapke liye Aaj ki Video:", protect_content=True)
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
            await update.message.reply_text(f"Invalid video index! Total videos stored: {len(videos)}")
            return

        vid = videos[vid_index]
        if vid["type"] == "video":
            await context.bot.send_video(chat_id=target_user_id, video=vid["file_id"], caption=vid.get("caption", "Specific Video from Admin"), protect_content=True)
        elif vid["type"] == "document":
            # FIX: was `video=vid["file_id"]` — send_document needs `document=`
            await context.bot.send_document(chat_id=target_user_id, document=vid["file_id"], caption=vid.get("caption", "Specific Video from Admin"), protect_content=True)

        await update.message.reply_text(f"Successfully sent video index {vid_index} to user {target_user_id}!")
    except Exception as e:
        await update.message.reply_text(f"Error sending specific video: {e}")


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


async def process_admin_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data["waiting_for_channel_data"] = False
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 4:
        await update.message.reply_text(
            "Format galat hai. Sahi format:\nchannel_id|name|price|days\n\nExample:\n-1001234567890|Premium Plan|299|30"
        )
        return
    channel_id, name, price_str, days_str = parts
    try:
        price = int(price_str)
        days = int(days_str)
    except ValueError:
        await update.message.reply_text("Price aur Days number mein hone chahiye.")
        return

    db_save_channel(channel_id, name, price, days)
    await update.message.reply_text(f"Channel saved!\n\nName: {name}\nPrice: {price}\nDays: {days}\nChannel ID: {channel_id}")


async def process_admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data["waiting_for_broadcast_message"] = False
    all_subs = db_get_all_subscriptions()
    distinct_users = {row["user_id"] for row in all_subs}

    if not distinct_users:
        await update.message.reply_text("Broadcast ke liye koi users nahi mile (abhi tak koi subscription record nahi hai).")
        return

    sent, failed = 0, 0
    for uid in distinct_users:
        try:
            await context.bot.send_message(chat_id=uid, text=text, protect_content=True)
            sent += 1
        except Exception as e:
            logging.error(f"Broadcast failed for {uid}: {e}")
            failed += 1

    await update.message.reply_text(f"Broadcast complete!\n\nSent: {sent}\nFailed: {failed}")


async def process_admin_free_access(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data["waiting_for_free_access"] = False
    parts = [p.strip() for p in text.split("|")]
    if len(parts) not in (2, 3):
        await update.message.reply_text(
            "Format galat hai. Sahi format:\nuser_id|channel_id|days (days optional)\n\nExample:\n123456789|-1001234567890|30"
        )
        return

    target_user_id_str, ch_id = parts[0], parts[1]
    managed_channels = db_get_channels()
    if ch_id not in managed_channels:
        await update.message.reply_text(f"Channel ID '{ch_id}' nahi mila. Pehle 'Add / Edit Channel' se add karein.")
        return

    try:
        target_user_id = int(target_user_id_str)
    except ValueError:
        await update.message.reply_text("user_id number hona chahiye.")
        return

    if len(parts) == 3:
        try:
            days = int(parts[2])
        except ValueError:
            await update.message.reply_text("Days number hona chahiye.")
            return
    else:
        days = managed_channels[ch_id]["days"]

    now = datetime.now()
    existing = db_get_subscription(target_user_id, ch_id)
    if existing and existing["expiry"] > now:
        expiry = existing["expiry"] + timedelta(days=days)
    else:
        expiry = now + timedelta(days=days)

    db_save_subscription(target_user_id, ch_id, expiry, now, 0)

    ch_name = managed_channels[ch_id]["name"]
    await update.message.reply_text(
        f"Free access diya gaya!\n\nUser: {target_user_id}\nChannel: {ch_name}\nValid until: {expiry.strftime('%Y-%m-%d %H:%M')}"
    )
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"Aapko '{ch_name}' ka free access mil gaya hai! Valid until: {expiry.strftime('%Y-%m-%d %H:%M')}.",
            protect_content=True
        )
    except Exception as e:
        logging.error(f"Could not notify user {target_user_id} of free access: {e}")


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    text = update.message.text

    if ADMIN_USER_ID and user_id == ADMIN_USER_ID:
        if context.user_data.get("waiting_for_channel_data"):
            await process_admin_add_channel(update, context, text)
            return
        if context.user_data.get("waiting_for_broadcast_message"):
            await process_admin_broadcast(update, context, text)
            return
        if context.user_data.get("waiting_for_free_access"):
            await process_admin_free_access(update, context, text)
            return
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
        "Aapka message admin tak pahuncha diya gaya hai. Admin jald hi aapko reply dega.",
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
            text=f"Admin Reply:\n\n{reply_text}",
            protect_content=True
        )
        await update.message.reply_text(f"Reply successfully sent to user {target_user_id}!")
    except Exception as e:
        await update.message.reply_text(f"Error sending reply: {e}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    managed_channels = db_get_channels()

    try:
        await _handle_button_data(update, context, query, user_id, data, managed_channels)
    except Exception as e:
        logging.error(f"button_handler error for data='{data}': {e}", exc_info=True)
        try:
            await query.message.reply_text("Kuch error aa gaya. Kripya /start karke phir try karein.")
        except Exception:
            pass


async def _handle_button_data(update, context, query, user_id, data, managed_channels):
    if data == "main_menu":
        await show_main_menu(update, context, edit=True)

    elif data == "show_plans":
        keyboard = []
        for ch_id, details in managed_channels.items():
            keyboard.append([
                InlineKeyboardButton(f"{details['name']} ({details['price']} / {details['days']} Days)", callback_data=f"buy_{ch_id}")
            ])
        keyboard.append([InlineKeyboardButton("Back", callback_data="main_menu")])
        await query.edit_message_text(
            text="Upgrade Your Plan:\nSelect a plan below to extend your subscription:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "help_support":
        help_text = (
            "Customer Support & Help:\n\n"
            "Agar aapko payment ya subscription mein koi bhi samasya aa rahi hai, toh aap seedha admin se sampark kar sakte hain.\n\n"
            "Niche likha gaya message type karein aur admin ko bhej denge:"
        )
        keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
        await query.edit_message_text(text=help_text, reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data["waiting_for_support"] = True

    elif data == "get_videos_info":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            active_subs = db_get_all_active_subscriptions(user_id)
            if not active_subs:
                await query.message.reply_text("Aapka koi active subscription nahi hai! Kripya pehle plan buy karein.")
                return

        videos = load_videos_from_file()
        if not videos:
            await query.message.reply_text("Filhal koi video available nahi hai.")
            return

        vid = videos[-1]
        await query.message.reply_text("Aapke liye Aaj ki Video:", protect_content=True)
        try:
            if vid["type"] == "video":
                await context.bot.send_video(chat_id=user_id, video=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)
            elif vid["type"] == "document":
                await context.bot.send_document(chat_id=user_id, document=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)
        except Exception as e:
            logging.error(f"Error in button video send: {e}")
            await query.message.reply_text("Video send karne mein error aaya.")

    elif data == "admin_panel":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        keyboard = [
            [InlineKeyboardButton("Add / Edit Channel", callback_data="admin_add_channel")],
            [InlineKeyboardButton("Manage Subscriptions", callback_data="admin_manage_subs")],
            [InlineKeyboardButton("Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("View Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("Back", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            text="Admin Control Panel:\nChoose an option below.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "admin_manage_subs":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        keyboard = [
            [InlineKeyboardButton("View Subscribers", callback_data="admin_view_subs")],
            [InlineKeyboardButton("Give Free Access", callback_data="admin_free_access")],
            [InlineKeyboardButton("Back", callback_data="admin_panel")]
        ]
        await query.edit_message_text(
            text="Manage Subscriptions:\nChoose an option below.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "admin_view_subs":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        all_subs = db_get_all_subscriptions()
        now = datetime.now()
        active = [row for row in all_subs if _safe_expiry(row) and _safe_expiry(row) > now]

        if not active:
            text = "Filhal koi active subscriber nahi hai."
        else:
            by_channel = {}
            for row in active:
                by_channel.setdefault(row["channel_id"], []).append(row)

            lines = [f"Active Subscribers: {len(active)}\n"]
            for ch_id, rows in by_channel.items():
                ch_name = managed_channels.get(ch_id, {}).get("name", ch_id)
                lines.append(f"\n{ch_name} ({len(rows)}):")
                for row in sorted(rows, key=lambda r: _safe_expiry(r)):
                    exp = _safe_expiry(row)
                    free_tag = " [FREE]" if not row.get("price_paid") else ""
                    lines.append(f"  • {row['user_id']} — until {exp.strftime('%Y-%m-%d')}{free_tag}")
            text = "\n".join(lines)

        keyboard = [[InlineKeyboardButton("Back", callback_data="admin_manage_subs")]]
        # Telegram caps messages at 4096 chars — chunk long lists
        chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)] or [text]
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1:
                await query.message.reply_text(chunk, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await query.message.reply_text(chunk)
        try:
            await query.answer()
        except Exception:
            pass

    elif data == "admin_free_access":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        context.user_data["waiting_for_free_access"] = True
        keyboard = [[InlineKeyboardButton("Back", callback_data="admin_manage_subs")]]
        await query.edit_message_text(
            text=(
                "Give Free Access:\n\n"
                "Is format mein reply karein:\n"
                "user_id|channel_id|days\n\n"
                "Example:\n123456789|-1001234567890|30\n\n"
                "(days optional hai — agar chhod diya (user_id|channel_id) to channel ke default days use honge.)"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "admin_add_channel":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        context.user_data["waiting_for_channel_data"] = True
        keyboard = [[InlineKeyboardButton("Back", callback_data="admin_panel")]]
        await query.edit_message_text(
            text=(
                "Add / Edit Channel:\n\n"
                "Reply is format mein ek message bhejein:\n"
                "channel_id|name|price|days\n\n"
                "Example:\n-1001234567890|Premium Plan|299|30\n\n"
                "(Agar channel_id already exist karta hai to overwrite ho jayega.)"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "admin_broadcast":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        context.user_data["waiting_for_broadcast_message"] = True
        keyboard = [[InlineKeyboardButton("Back", callback_data="admin_panel")]]
        await query.edit_message_text(
            text=(
                "Broadcast Message:\n\n"
                "Jo message bhejna hai wo type karke reply karein.\n"
                "Yeh sabhi users ko jayega jinka kabhi bhi koi subscription record raha ho."
            ),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "admin_stats":
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return
        all_subs = db_get_all_subscriptions()
        now = datetime.now()
        total_channels = len(managed_channels)
        total_subs = len(all_subs)
        active_subs = 0
        total_revenue = 0
        distinct_users = set()
        for row in all_subs:
            distinct_users.add(row["user_id"])
            total_revenue += row.get("price_paid", 0) or 0
            try:
                if datetime.fromisoformat(row["expiry"]) > now:
                    active_subs += 1
            except Exception:
                pass
        stats_text = (
            "Bot Stats:\n\n"
            f"Total Channels/Plans: {total_channels}\n"
            f"Total Subscriptions (all time): {total_subs}\n"
            f"Currently Active Subscriptions: {active_subs}\n"
            f"Unique Paying Users: {len(distinct_users)}\n"
            f"Total Revenue Collected: {total_revenue}"
        )
        keyboard = [[InlineKeyboardButton("Back", callback_data="admin_panel")]]
        await query.edit_message_text(text=stats_text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_"):
        ch_id = data.replace("buy_", "")
        if ch_id not in managed_channels:
            await query.edit_message_text(text="Invalid channel selection.")
            return

        active_subs = db_get_all_active_subscriptions(user_id)
        if ch_id in active_subs:
            await query.answer("Aapka yeh subscription pehle se active hai!", show_alert=True)
            return

        details = managed_channels[ch_id]
        if not UPI_ID:
            await query.edit_message_text(
                text="UPI Payment is not configured!\n\nPlease contact admin for payment details."
            )
            logging.error("UPI_ID is not set in environment variables")
            return

        qr_caption = (
            f"Plan: {details['name']} ({details['days']} Days)\n"
            f"Amount: {details['price']}\n\n"
            "1. Scan the QR code using any UPI app to pay.\n"
            "2. After payment, click the 'I Have Paid' button below."
        )
        upi_string = f"upi://pay?pa={UPI_ID}&pn=Quick-Deals&am={details['price']}&tn=Subscription%20Payment"
        qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={quote(upi_string)}"

        keyboard = [
            [InlineKeyboardButton("I Have Paid", callback_data=f"paid_{ch_id}")],
            [InlineKeyboardButton("Back", callback_data="main_menu")]
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
                protect_content=True
            )
        except Exception as e:
            logging.error(f"Error generating QR code: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Error generating QR code!\n\nPlease contact admin:\nUPI: {UPI_ID}\nAmount: {details['price']}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                protect_content=True
            )

    elif data.startswith("paid_"):
        ch_id = data.replace("paid_", "")
        # FIX: was `managed_channels[ch_id]` — KeyError if the channel was deleted meanwhile
        details = managed_channels.get(ch_id)
        if not details:
            await query.answer("Yeh plan ab available nahi hai.", show_alert=True)
            return

        try:
            await query.edit_message_caption(
                caption="Payment verification pending!\nYour request has been sent to the admin."
            )
        except Exception:
            pass

        if ADMIN_USER_ID:
            admin_keyboard = [
                [
                    InlineKeyboardButton("Approve", callback_data=f"app_{user_id}_{ch_id}"),
                    InlineKeyboardButton("Reject", callback_data=f"rej_{user_id}")
                ]
            ]
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"New Payment Verification Request!\n\n"
                     f"User ID: {user_id}\n"
                     f"Channel ID: {ch_id}\n"
                     f"Amount: {details['price']}",
                reply_markup=InlineKeyboardMarkup(admin_keyboard),
                protect_content=True
            )

    elif data.startswith("app_"):
        # NOTE: original file had this exact block duplicated right after itself —
        # the second copy was unreachable dead code, so it's been removed here.
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
                text=f"Payment Approved! Aapka subscription active ho gaya hai (Valid until: {expiry.strftime('%Y-%m-%d %H:%M')}).\n\nEk Aaj ki Video:",
                protect_content=True
            )
            videos = load_videos_from_file()
            if videos:
                vid = videos[-1]
                if vid["type"] == "video":
                    await context.bot.send_video(chat_id=target_user_id, video=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)
                elif vid["type"] == "document":
                    # FIX: was `video=vid["file_id"]` — send_document needs `document=`
                    await context.bot.send_document(chat_id=target_user_id, document=vid["file_id"], caption=vid.get("caption", ""), protect_content=True)

            await query.edit_message_text(text=f"Approved and today's video sent to user {target_user_id}!")
        except Exception as e:
            await query.edit_message_text(text=f"Error: {e}")

    elif data.startswith("rej_"):
        if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
            await query.answer("Access denied.", show_alert=True)
            return

        _, target_user_id = data.split("_")
        target_user_id = int(target_user_id)
        await context.bot.send_message(chat_id=target_user_id, text="Your payment verification was rejected.", protect_content=True)
        await query.edit_message_text(text=f"Rejected user {target_user_id}.")


# ---------------------------------------------------------------------------
# NOTE: GitHub's page only let me fetch content up to here (~line 490) —
# whatever startup/run block your repo has past this point (ApplicationBuilder,
# handler registration, run_polling) is NOT included above, so I could not
# edit it. Below is a standard reconstruction based on the handlers defined
# in this file, matching what Procfile expects ("python bot.py"). Please
# compare it against what's actually in your repo before replacing anything,
# since I never saw your original main().
# ---------------------------------------------------------------------------

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Unhandled exception: {context.error}", exc_info=context.error)


def main():
    if not TOKEN:
        logging.error("TOKEN environment variable is not set. Exiting.")
        return

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_error_handler(global_error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("sendvideo", send_specific_video_command))
    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_storage_channel_post))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))

    logging.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
