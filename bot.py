import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from supabase import create_client, Client

TOKEN = os.getenv("TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))
UPI_ID = os.getenv("UPI_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


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
    
    if user_id == ADMIN_USER_ID:
        text = "👑 **Admin Panel / Status:**\nAapke paas Admin access hai. Naye plans add karne ke liye `/addchannel` command use karein."
        keyboard = [
            [InlineKeyboardButton("🎬 Get Daily Videos (/video)", callback_data="get_videos_info")],
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
                "Daily videos aur channel access ke liye niche diye gaye plan par click karein:"
            )
            for ch_id, details in managed_channels.items():
                keyboard.append([
                    InlineKeyboardButton(f"🚀 {details['name']} ({details['price']}₹ / {details['days']} Days)", callback_data=f"buy_{ch_id}")
                ])

        keyboard.append([InlineKeyboardButton("🎬 Get Daily Videos (/video)", callback_data="get_videos_info")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown", protect_content=True)


async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        active_subs = db_get_all_active_subscriptions(user_id)
        if not active_subs:
            await update.message.reply_text(
                "❌ **Aapne subscription nahi liya hai!**\n\nDaily videos access karne ke liye pehle /start dabakar plan buy karein.",
                parse_mode="Markdown",
                protect_content=True
            )
            return
        
    await update.message.reply_text(
        "🎬 **Aapke liye Aaj ki Videos:**\n\n"
        "*(Note: Storage channel se media access karne ke liye channel ID configure honi chahiye.)*",
        parse_mode="Markdown",
        protect_content=True
    )


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

    elif data == "get_videos_info":
        await query.answer("💡 Aap kabhi bhi chat mein /video likh kar apni daily videos access kar sakte hain!", show_alert=True)

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
        qr_caption = (
            f"🛍️ **Plan:** {details['name']} ({details['days']} Days)\n"
            f"💰 **Amount:** ₹{details['price']}\n\n"
            "1️⃣ Scan the QR code using any UPI app to pay.\n"
            "2️⃣ After payment, click the **'I Have Paid'** button below."
        )
        
        qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=upi://pay?pa={UPI_ID}&am=" + str(details['price'])

        keyboard = [
            [InlineKeyboardButton("✅ I Have Paid", callback_data=f"paid_{ch_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        
        await query.message.delete()
        await context.bot.send_photo(
            chat_id=user_id,
            photo=qr_image_url,
            caption=qr_caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
            protect_content=True
        )

    elif data.startswith("paid_"):
        ch_id = data.replace("paid_", "")
        details = managed_channels[ch_id]
        
        await query.edit_message_caption(
            caption="⏳ **Payment verification pending!**\nYour request has been sent to the admin.",
            parse_mode="Markdown"
        )

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

    elif data.startswith("app_") and user_id == ADMIN_USER_ID:
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
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=ch_id,
                member_limit=1,
                expire_date=int(expiry.timestamp()),
            )
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 **Payment Approved!** Subscription updated until {expiry.strftime('%Y-%m-%d %H:%M')}.\n"
                     f"⚠️ *Note:* Yeh invite link sirf **ek baar** use ho sakta hai.\n\n"
                     f"🔗 **Your single-use invite link:** {invite_link.invite_link}",
                parse_mode="Markdown",
                protect_content=True
            )
            await query.edit_message_text(text=f"✅ Approved for user `{target_user_id}`!", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(text=f"❌ Error generating invite link: {e}")

    elif data.startswith("rej_") and user_id == ADMIN_USER_ID:
        _, target_user_id = data.split("_")
        target_user_id = int(target_user_id)
        
        await context.bot.send_message(chat_id=target_user_id, text="❌ Your payment verification was rejected.", protect_content=True)
        await query.edit_message_text(text=f"❌ Rejected user `{target_user_id}`.")

    elif data == "admin_panel" and user_id == ADMIN_USER_ID:
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

    elif data == "admin_sub_list" and user_id == ADMIN_USER_ID:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        subs = db_get_all_subscriptions()
        text = "📋 **Subscribers List Database:**\n\n"
        
        if not subs:
            text += "No active subscribers found."
        else:
            now = datetime.now()
            for row in subs:
                status = "🟢 Active" if datetime.fromisoformat(row["expiry"]) > now else "🔴 Expired"
                text += f"👤 User: `{row['user_id']}`\n📦 Ch: `{row['channel_id']}`\nStatus: {status}\nExp: `{row['expiry'][:16]}`\n\n"

        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_channel_help" and user_id == ADMIN_USER_ID:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        await query.edit_message_text(
            text="To add or update a channel plan price/days, send command in chat:\n`/addchannel -100xxxxxxxxxx Channel_Name Price Days`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "admin_free_help" and user_id == ADMIN_USER_ID:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        await query.edit_message_text(
            text="To give free entry without payment, send command in chat:\n`/giveaccess user_id channel_id days`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "main_menu":
        await query.message.delete()
        await show_main_menu(update, context, edit=False)


async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    
    args = context.args
    if len(args) != 4:
        await update.message.reply_text("Usage: /addchannel -100xxxxxxxxxx Channel_Name Price Days")
        return

    ch_id, name, price, days = args[0], args[1], int(args[2]), int(args[3])
    db_save_channel(ch_id, name, price, days)
    await update.message.reply_text(f"✅ Channel Plan saved to Database!\nChannel: {name}\nPrice: ₹{price}\nValidity: {days} Days")


async def give_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
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
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=ch_id,
            member_limit=1,
            expire_date=int(expiry.timestamp()),
        )
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 **Access Granted by Admin!** Valid until {expiry.strftime('%Y-%m-%d %H:%M')}.\n"
                 f"⚠️ *Note:* Yeh invite link sirf ek baar use ho sakta hai.\n\n"
                 f"🔗 **Your invite link:** {invite_link.invite_link}",
            protect_content=True
        )
        await update.message.reply_text(f"✅ Successfully granted access to user `{target_user_id}` for {days} days!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error generating invite link: {e}")


def main():
    if not TOKEN:
        raise ValueError("No TOKEN found in environment variables!")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("addchannel", add_channel_command))
    app.add_handler(CommandHandler("giveaccess", give_access_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Dynamic Channel Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
        
