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

# Configuration
TOKEN = "8237192414:AAGC6N4dattjPSjBVT6bZLtP6R4LeARGLCw"
CHANNEL_ID = "https://t.me/+-tWVy6mFLJozMmZl"  # Replace with your channel ID
ADMIN_USER_ID = 123456789  # Replace with your Telegram Admin User ID
SUBSCRIPTION_PRICE_STARS = 250  # Cost in Telegram Stars (XTR)
SUBSCRIPTION_DAYS = 30

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

subscriptions = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton(f"Subscribe ({SUBSCRIPTION_PRICE_STARS} ⭐)", callback_data="buy_stars_sub")],
        [InlineKeyboardButton("Check Status", callback_data="check_status")],
    ]
    if user.id == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Hello {user.first_name}! Welcome to the channel subscription bot.\n"
        f"Gain instant access to {CHANNEL_ID} for 30 days using Telegram Stars.",
        reply_markup=reply_markup,
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buy_stars_sub":
        title = "Private Channel Subscription"
        description = f"30-day access to {CHANNEL_ID}"
        payload = "channel_subscription_payload"
        currency = "XTR"
        prices = [LabeledPrice("Subscription", SUBSCRIPTION_PRICE_STARS)]

        await context.bot.send_invoice(
            chat_id=user_id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",
            currency=currency,
            prices=prices,
        )

    elif query.data == "check_status":
        expiry = subscriptions.get(user_id)
        if expiry and expiry > datetime.now():
            await query.edit_message_text(
                text=f"Your subscription is active until: {expiry.strftime('%Y-%m-%d %H:%M')}"
            )
        else:
            await query.edit_message_text(
                text="You do not have an active subscription. Click /start to subscribe."
            )

    elif query.data == "admin_panel" and user_id == ADMIN_USER_ID:
        active_count = sum(1 for exp in subscriptions.values() if exp > datetime.now())
        keyboard = [
            [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 View Subscribers", callback_data="admin_list")],
            [InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu")],
        ]
        await query.edit_message_text(
            text=f"⚙️ **Admin Control Panel**\n\nActive Subscribers: {active_count}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif query.data == "admin_stats" and user_id == ADMIN_USER_ID:
        active_count = sum(1 for exp in subscriptions.values() if exp > datetime.now())
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        await query.edit_message_text(
            text=f"📊 **Bot Statistics**\n\nTotal tracked records: {len(subscriptions)}\nActive Subscriptions: {active_count}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif query.data == "admin_list" and user_id == ADMIN_USER_ID:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
        if not subscriptions:
            text = "No subscribers found."
        else:
            text = "👥 **Subscribers List:**\n"
            for uid, exp in subscriptions.items():
                status = "Active" if exp > datetime.now() else "Expired"
                text += f"- ID: `{uid}` | Expires: {exp.strftime('%Y-%m-%d')} ({status})\n"
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif query.data == "main_menu":
        keyboard = [
            [InlineKeyboardButton(f"Subscribe ({SUBSCRIPTION_PRICE_STARS} ⭐)", callback_data="buy_stars_sub")],
            [InlineKeyboardButton("Check Status", callback_data="check_status")],
        ]
        if user_id == ADMIN_USER_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
        await query.edit_message_text(
            text="Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload != "channel_subscription_payload":
        await query.answer(ok=False, error_message="Something went wrong.")
    else:
        await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    expiry = datetime.now() + timedelta(days=SUBSCRIPTION_DAYS)
    subscriptions[user_id] = expiry

    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=int(expiry.timestamp()),
        )
        await update.message.reply_text(
            f"Payment successful! Thank you for subscribing. 🎉\n"
            f"Your access is valid until {expiry.strftime('%Y-%m-%d %H:%M')}.\n\n"
            f"Use this single-use link to join: {invite_link.invite_link}"
        )
    except Exception as e:
        await update.message.reply_text("Payment received, but failed to generate invite link. Contact admin.")
        logging.error(f"Invite error: {e}")


async def check_subscriptions_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    expired_users = [uid for uid, expiry in subscriptions.items() if expiry <= now]

    for user_id in expired_users:
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id, only_if_banned=True)
            await context.bot.send_message(
                chat_id=user_id,
                text="Your 30-day channel subscription has expired and you have been removed.",
            )
            del subscriptions[user_id]
        except Exception as e:
            logging.error(f"Failed to kick user {user_id}: {e}")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    job_queue = app.job_queue
    job_queue.run_repeating(check_subscriptions_job, interval=3600, first=10)

    print("Bot with Admin Panel running...")
    app.run_polling()


if __name__ == "__main__":
    main()
    
