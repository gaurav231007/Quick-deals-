import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Safe fallback so it never crashes if Railway environment variables are missing
TOKEN = os.getenv("TOKEN") or "8237192414:AAGC6N4dattjPSjBVT6bZLtP6R4LeARGLCw"
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "5409176951"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

managed_channels = {
    "-1004487998151": {"price": 0, "days": 30}
}

subscriptions = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    keyboard = []
    for ch_id, details in managed_channels.items():
        keyboard.append([
            InlineKeyboardButton(f"Subscribe to Channel ({details['price']} ⭐)", callback_data=f"sub_{ch_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("Check Status", callback_data="check_status")])
    if user.id == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Hello {user.first_name}! Welcome to the channel subscription bot.\n"
        "Choose an option below and purchase access securely using Telegram Stars.",
        reply_markup=reply_markup,
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("sub_"):
        ch_id = data.replace("sub_", "")
        if ch_id not in managed_channels:
            await query.edit_message_text(text="Invalid channel selection.")
            return

        price = managed_channels[ch_id]["price"]
        days = managed_channels[ch_id]["days"]
        
        title = "Private Channel Subscription"
        description = f"{days}-day access to channel"
        payload = f"sub_pay_{ch_id}"
        currency = "XTR"
        prices = [LabeledPrice("Subscription", price)]

        await context.bot.send_invoice(
            chat_id=user_id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",
            currency=currency,
            prices=prices,
        )

    elif data == "check_status":
        user_subs = subscriptions.get(user_id, {})
        active_subs = {ch: exp for ch, exp in user_subs.items() if exp > datetime.now()}
        
        if not active_subs:
            text = "You do not have any active subscriptions."
        else:
            text = "📱 **Your Active Subscriptions:**\n"
            for ch_id, expiry in active_subs.items():
                text += f"- Channel ID `{ch_id}`: Active until {expiry.strftime('%Y-%m-%d %H:%M')}\n"
        await query.edit_message_text(text=text, parse_mode="Markdown")

    elif data == "admin_panel" and user_id == ADMIN_USER_ID:
        active_total = sum(
            1 for u_subs in subscriptions.values() 
            for exp in u_subs.values() 
            if exp > datetime.now()
        )
        keyboard = [
            [InlineKeyboardButton("📊 Stats & List", callback_data="admin_stats")],
            [InlineKeyboardButton("➕ Add/Update Channel", callback_data="admin_add_channel")],
            [InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu")],
        ]
        await query.edit_message_text(
            text=f"⚙️ **Admin Control Panel**\n\nTotal Active Subscriptions across all channels: {active_total}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "admin_stats" and user_id == ADMIN_USER_ID:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        text = "📊 **Subscriber Tracking Details:**\n\n"
        
        if not subscriptions:
            text += "No subscription records found yet."
        else:
            for uid, u_subs in subscriptions.items():
                for ch_id, exp in u_subs.items():
                    status = "Active" if exp > datetime.now() else "Expired"
                    text += f"User `{uid}` -> `{ch_id}` ({status}, Exp: {exp.strftime('%Y-%m-%d')})\n"
                    
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_add_channel" and user_id == ADMIN_USER_ID:
        await query.edit_message_text(
            text="To add or update a channel, use command in chat:\n`/addchannel -100xxxxxxxxxx price_in_stars days`\n\nExample: `/addchannel -1004487998151 250 30`",
            parse_mode="Markdown"
        )

    elif data == "main_menu":
        keyboard = []
        for ch_id, details in managed_channels.items():
            keyboard.append([InlineKeyboardButton(f"Subscribe to Channel ({details['price']} ⭐)", callback_data=f"sub_{ch_id}")])
        keyboard.append([InlineKeyboardButton("Check Status", callback_data="check_status")])
        if user_id == ADMIN_USER_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
        await query.edit_message_text(text="Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))


async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Usage: /addchannel -100xxxxxxxxxx price_in_stars days")
        return

    ch_id, price, days = args[0], int(args[1]), int(args[2])
    managed_channels[ch_id] = {"price": price, "days": days}
    await update.message.reply_text(f"Successfully added/updated {ch_id} with price {price} ⭐ for {days} days!")


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if not query.invoice_payload.startswith("sub_pay_"):
        await query.answer(ok=False, error_message="Something went wrong.")
    else:
        await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    payload = update.message.successful_payment.invoice_payload
    ch_id = payload.replace("sub_pay_", "")
    
    days = managed_channels.get(ch_id, {}).get("days", 30)
    expiry = datetime.now() + timedelta(days=days)
    
    if user_id not in subscriptions:
        subscriptions[user_id] = {}
    subscriptions[user_id][ch_id] = expiry

    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=ch_id,
            member_limit=1,
            expire_date=int(expiry.timestamp()),
        )
        await update.message.reply_text(
            f"Payment successful! 🎉 Access granted until {expiry.strftime('%Y-%m-%d %H:%M')}.\n\n"
            f"Your exclusive single-use invite link: {invite_link.invite_link}"
        )
    except Exception as e:
        await update.message.reply_text("Payment received, but failed to generate invite link. Ensure bot is an administrator with add users permission in the channel.")
        logging.error(f"Invite error for {ch_id}: {e}")


async def check_subscriptions_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    for user_id, user_subs in list(subscriptions.items()):
        for ch_id, expiry in list(user_subs.items()):
            if expiry <= now:
                try:
                    await context.bot.ban_chat_member(chat_id=ch_id, user_id=user_id)
                    await context.bot.unban_chat_member(chat_id=ch_id, user_id=user_id, only_if_banned=True)
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="Your channel subscription has expired. You have been removed.",
                    )
                    del subscriptions[user_id][ch_id]
                except Exception as e:
                    logging.error(f"Failed to remove user {user_id} from {ch_id}: {e}")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addchannel", add_channel_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    job_queue = app.job_queue
    job_queue.run_repeating(check_subscriptions_job, interval=3600, first=10)

    print("Secure multi-channel subscription bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
    
