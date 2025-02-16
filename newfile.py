import sqlite3
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

TOKEN = "7427344544:AAEZuSROcoyx9oh0pVMe4rb_P_hkHoIKLLo"  # Replace with your bot token

# Database setup
conn = sqlite3.connect("game_bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, current_number INTEGER, attempts_left INTEGER DEFAULT 3, upi_id TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS withdrawals (user_id INTEGER, upi_id TEXT, amount INTEGER, status TEXT, request_time INTEGER)")
conn.commit()

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0))
        conn.commit()

    # Displaying game rules and how to play
    game_info = (
        "👋 Welcome to the Game Bot!\n\n"
        "🎮 **How to Play**:\n"
        "- Type `/play` to start the game.\n"
        "- You have 3 chances to guess the correct number between 1 and 10.\n"
        "- If you guess correctly, you earn ₹1. If you lose, you lose ₹1.\n"
        "- Your balance will be displayed with the `/balance` command.\n"
        "- Once you have ₹25, you can request a withdrawal.\n\n"
        "💡 **To Start the Game**: Type `/play`!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎮 Start Game", callback_data="start_game")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(game_info, reply_markup=reply_markup)

# Play command (start the game)
async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    random_number = random.randint(1, 10)
    cursor.execute("UPDATE users SET current_number = ?, attempts_left = 3 WHERE user_id = ?", (random_number, user_id))
    conn.commit()
    await update.message.reply_text("🎲 Guess a number between 1 and 10. You have 3 chances!")

# Handle guesses
async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    guess = update.message.text.strip()
    
    if not guess.isdigit():
        await update.message.reply_text("⚠️ Please enter a valid number.")
        return

    guess = int(guess)
    cursor.execute("SELECT current_number, attempts_left, balance FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()

    if not user_data or user_data[1] == 0:
        await update.message.reply_text("❌ No active game. Type `/play` to start a new game.")
        return

    correct_number, attempts_left, balance = user_data

    if guess == correct_number:
        balance += 1
        cursor.execute("UPDATE users SET balance = ?, current_number = NULL, attempts_left = 0 WHERE user_id = ?", (balance, user_id))
        conn.commit()
        await update.message.reply_text(f"🎉 Correct! You won ₹1. Balance: ₹{balance}\nType `/play` to play again.")
    else:
        attempts_left -= 1
        if attempts_left == 0:
            balance -= 1
            cursor.execute("UPDATE users SET balance = ?, current_number = NULL, attempts_left = 0 WHERE user_id = ?", (balance, user_id))
            conn.commit()
            await update.message.reply_text(f"❌ Wrong! Correct number was {correct_number}. You lost ₹1. Balance: ₹{balance}\nType `/play` to try again.")
        else:
            cursor.execute("UPDATE users SET attempts_left = ? WHERE user_id = ?", (attempts_left, user_id))
            conn.commit()
            await update.message.reply_text(f"❌ Wrong! {attempts_left} chances left. Try again.")

# Check balance
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]
    
    keyboard = []
    if balance >= 25:
        keyboard.append([InlineKeyboardButton("💸 Withdraw ₹25", callback_data="withdraw")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"💰 Your Balance: ₹{balance}", reply_markup=reply_markup)

# Withdrawal function
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.message.chat_id
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]

    if balance >= 25:
        await query.message.reply_text("💸 Please send your UPI ID to complete the withdrawal request.")
        cursor.execute("UPDATE users SET upi_id = NULL WHERE user_id = ?", (user_id,))
        conn.commit()
        return
    else:
        await query.message.reply_text("❌ Minimum ₹25 required to withdraw.")

# Handle UPI ID submission
async def handle_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    upi_id = update.message.text.strip()

    cursor.execute("UPDATE users SET upi_id = ? WHERE user_id = ?", (upi_id, user_id))
    conn.commit()

    # Save withdrawal request with a 1-hour wait time
    request_time = int(time.time())
    cursor.execute("INSERT INTO withdrawals (user_id, upi_id, amount, status, request_time) VALUES (?, ?, ?, ?, ?)", 
                   (user_id, upi_id, 25, "Pending", request_time))
    conn.commit()

    await update.message.reply_text(f"✅ Withdrawal request for ₹25 submitted!\nPlease wait for 1 hour for the processing.")
    await update.message.reply_text("⏳ You can check the status of your withdrawal with /balance.")

# Admin command to check pending withdrawals
async def check_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT user_id, upi_id, amount, status, request_time FROM withdrawals WHERE status = 'Pending'")
    withdrawals = cursor.fetchall()

    if not withdrawals:
        await update.message.reply_text("✅ No pending withdrawals.")
        return

    message = "📝 Pending Withdrawals:\n"
    for withdrawal in withdrawals:
        request_time = withdrawal[4]
        time_left = max(0, 3600 - (int(time.time()) - request_time))
        message += f"👤 User: {withdrawal[0]}, Amount: ₹{withdrawal[2]}, UPI: {withdrawal[1]}, Time Left: {time_left // 60} mins\n"

    await update.message.reply_text(message)

# Main function
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("check_withdrawals", check_withdrawals))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_guess))
    app.add_handler(CallbackQueryHandler(withdraw, pattern="withdraw"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_upi))  # For UPI ID submission

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()