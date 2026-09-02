import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TOKEN") or "8237192414:AAGC6N4dattjPSjBVT6bZLtP6R4LeARGLCw"
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "5409176951"))
UPI_ID = "9507846346@ptaxis"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

managed_channels = {
    "-1004487998151": {"name": "Testing Channel", "price": 29, "days": 30}
}

REQUIRED_JOIN_CHANNEL = "@YourUpdateChannel"

subscriptions = {}  
pending_payments = {} 
daily_videos_list = [] # Admin dwara bheje gaye direct videos/files ki list


async def check_membership(bot, user_id, channel):
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception:
        pass
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if REQUIRED_JOIN_CHANNEL != "@YourUpdateChannel":
        is_joined = await check_membership(context.bot, user.id, REQUIRED_JOIN_CHANNEL)
        if not is_joined:
            keyboard = [
                [InlineKeyboardButton("📢 Join Channel To Use Bot", url=f"https://t.me/{REQUIRED_JOIN_CHANNEL.replace('@','')}")],
                [InlineKeyboardButton("✅ Joined / Verify", callback_data="verify_join")]
            ]
            await update.message.reply_text(
                "⚠️ **Please join our update channel first to use this bot!**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                protect_content=True
            )
            return

    await show_main_menu(update, context)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    keyboard = []
    for ch_id, details in managed_channels.items():
        keyboard.append([
            InlineKeyboardButton(f"🚀 {details['name']} ({details['price']}₹ / {details['days']} Days)", callback_data=f"buy_{ch_id}")
        ])
    keyboard.append([InlineKeyboardButton("📊 Check My Status", callback_data="check_status")])
    
    if update.effective_user.id == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"👋 Hello {update.effective_user.first_name}!\n\n"
        "✨ **Welcome to Private Channel Subscription Bot.**\n"
        "Select a plan below to get daily content and access."
    )

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown", protect_content=True)


async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = datetime.now()
    
    user_subs = subscriptions.get(user_id, {})
    active_subs = {ch: info for ch, info in user_subs.items() if info["expiry"] > now}
    
    if not active_subs:
        await update.message.reply_text("❌ Aapke paas koi active subscription nahi hai. Pehle plan buy karein!", protect_content=True)
        return
        
    if not daily_videos_list:
        await update.message.reply_text("📭 Filhal koi video available nahi hai. Thodi der baad try karein!", protect_content=True)
        return

    await update.message.reply_text("🎬 **Aapke liye Aaj ki Videos:**", parse_mode="Markdown", protect_content=True)
    
    # Har stored video ko user ko direct forward-protected bhej diya jayega
    for vid_info in daily_videos_list:
        try:
            if vid_info["type"] == "video":
                await context.bot.send_video(
                    chat_id=user_id,
                    video=vid_info["file_id"],
                    caption=vid_info.get("caption", ""),
                    protect_content=True
                )
            elif vid_info["type"] == "document":
                await context.bot.send_document(
                    chat_id=user_id,
                    document=vid_info["file_id"],
                    caption=vid_info.get("caption", ""),
                    protect_content=True
                )
        except Exception as e:
            logging.error(f"Error sending video to {user_id}: {e}")


async def handle_admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin jab bhi bot ko direct video ya document bhejega, woh save ho jayegi"""
    if update.effective_user.id != ADMIN_USER_ID:
        return

    message = update.message
    if message.video:
        file_id = message.video.file_id
        caption = message.caption or ""
        daily_videos_list.append({"type": "video", "file_id": file_id, "caption": caption})
        await message.reply_text(f"✅ Video successfully added to queue! Total videos: {len(daily_videos_list)}")
    elif message.document:
        file_id = message.document.file_id
        caption = message.caption or ""
        daily_videos_list.append({"type": "document", "file_id": file_id, "caption": caption})
        await message.reply_text(f"✅ Document/Video file added to queue! Total items: {len(daily_videos_list)}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "verify_join":
        if REQUIRED_JOIN_CHANNEL != "@YourUpdateChannel" and await check_membership(context.bot, user_id, REQUIRED_JOIN_CHANNEL):
            await query.message.delete()
            await show_main_menu(update, context)
        else:
            await query.answer("❌ You haven't joined the channel yet!", show_alert=True)

    elif data.startswith("buy_"):
        ch_id = data.replace("buy_", "")
        if ch_id not in managed_channels:
            await query.edit_message_text(text="Invalid channel selection.")
            return

        details = managed_channels[ch_id]
        pending_payments[user_id] = ch_id

        qr_caption = (
            f"🛍️ **Plan:** {details['days']} Days Access + Daily Videos\n"
            f"💰 **Amount:** ₹{details['price']}\n\n"
            "1️⃣ Scan the QR code using any UPI app to pay.\n"
            "2️⃣ After payment, click the **'I Have Paid'** button below."
        )
        
        qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=upi://pay?pa={UPI_ID}&am=" + str(details['price'])

        keyboard = [
            [InlineKeyboardButton("✅ I Have Paid", callback_data="i_have_paid")],
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

    elif data == "i_have_paid":
        ch_id = pending_payments.get(user_id)
        if not ch_id:
            await query.edit_message_text(text="Session expired. Please start again with /start")
            return

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
                 f"👤 **User:** {query.from_user.first_name} (`{user_id}`)\n"
                 f"📦 **Channel:** `{ch_id}`\n"
                 f"💵 **Amount:** ₹{details['price']}",
            reply_markup=InlineKeyboardMarkup(admin_keyboard),
            parse_mode="Markdown",
            protect_content=True
        )

    elif data.startswith("app_") and user_id == ADMIN_USER_ID:
        _, target_user_id, ch_id = data.split("_")
        target_user_id = int(target_user_id)
        
        details = managed_channels[ch_id]
        days = details["days"]
        now = datetime.now()
        expiry = now + timedelta(days=days)

        if target_user_id not in subscriptions:
            subscriptions[target_user_id] = {}
        
        subscriptions[target_user_id][ch_id] = {
            "expiry": expiry,
            "start_date": now
        }

        try:
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=ch_id,
                member_limit=1,
                expire_date=int(expiry.timestamp()),
            )
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 **Payment Approved!** Access granted until {expiry.strftime('%Y-%m-%d %H:%M')}.\n"
                     f"💡 Ab aap `/video` command bhej kar direct videos access kar sakte hain!\n\n"
                     f"🔗 **Your single-use invite link:** {invite_link.invite_link}",
                parse_mode="Markdown",
                protect_content=True
            )
            await query.edit_message_text(text=f"✅ Approved successfully for user `{target_user_id}`!", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(text=f"❌ Error generating invite link: {e}")

    elif data.startswith("rej_") and user_id == ADMIN_USER_ID:
        _, target_user_id = data.split("_")
        target_user_id = int(target_user_id)
        
        await context.bot.send_message(
            chat_id=target_user_id,
            text="❌ Your payment verification was rejected by the admin.",
            protect_content=True
        )
        await query.edit_message_text(text=f"❌ Payment rejected for user `{target_user_id}`.")

    elif data == "check_status":
        user_subs = subscriptions.get(user_id, {})
        now = datetime.now()
        active_subs = {ch: info for ch, info in user_subs.items() if info["expiry"] > now}
        
        if not active_subs:
            text = "❌ You do not have any active subscriptions."
        else:
            text = "📱 **Your Active Subscriptions:**\n"
            for ch_id, info in active_subs.items():
                ch_name = managed_channels.get(ch_id, {}).get("name", "Channel")
                text += f"- {ch_name}: Active until {info['expiry'].strftime('%Y-%m-%d %H:%M')}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        await query.message.delete()
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown", protect_content=True)

    elif data == "admin_panel" and user_id == ADMIN_USER_ID:
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            text=f"⚙️ **Admin Control Panel**\n\nActive Managed Channels: {len(managed_channels)}\nStored Videos in Queue: {len(daily_videos_list)}\n\n*(Note: Videos add karne ke liye seedha bot chat mein video bhej dein)*",
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
    managed_channels[ch_id] = {"name": name, "price": price, "days": days}
    await update.message.reply_text(f"Successfully added/updated {name} with price ₹{price} for {days} days!")


async def check_subscriptions_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    for user_id, user_subs in list(subscriptions.items()):
        for ch_id, info in list(user_subs.items()):
            if info["expiry"] <= now:
                try:
                    await context.bot.ban_chat_member(chat_id=ch_id, user_id=user_id)
                    await context.bot.unban_chat_member(chat_id=ch_id, user_id=user_id, only_if_banned=True)
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="⏰ Your channel subscription has expired. You have been removed.",
                        protect_content=True
                    )
                    del subscriptions[user_id][ch_id]
                except Exception as e:
                    logging.error(f"Failed to remove user {user_id} from {ch_id}: {e}")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("addchannel", add_channel_command))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.ALL, handle_admin_upload))
    app.add_handler(CallbackQueryHandler(button_handler))

    job_queue = app.job_queue
    job_queue.run_repeating(check_subscriptions_job, interval=3600, first=10)

    print("Direct Video Delivery Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
        
