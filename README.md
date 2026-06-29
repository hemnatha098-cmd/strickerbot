# Telegram Group Sticker & GIF Deleter Bot

A production-ready Telegram bot built with Python and the `python-telegram-bot` (v20+) library. This bot automatically identifies, logs, and deletes sticker and GIF (animation) messages from Telegram groups after a customizable time delay. It operates completely in-memory, avoiding the need for databases.

---

## 📂 Project Directory Structure

```text
stricker bot/
│
├── .env.example       # Example configuration file for environment variables
├── .env               # Private configuration file (contains your actual Bot Token)
├── requirements.txt   # List of library dependencies
├── bot.py             # Main entry point containing bot handlers and scheduler
└── README.md          # Project instructions and documentation
```

---

## 🛠️ Required Administrator Permissions

To function correctly in a group, the bot must be promoted to an **Administrator** with the following permissions:

1. **Delete Messages** (Required)  
   Allows the bot to delete sticker and GIF messages on behalf of the group.
2. **Read Messages / Access Messages** (Required)  
   Allows the bot to receive update events when messages are posted in the group. If the bot's privacy mode is active and it is not an administrator, it won't receive sticker or GIF messages from regular users. Promoting it to Admin bypasses Privacy Mode.

*Note: The bot does **not** need other administrative permissions (e.g., Ban Users, Add Admins, Pin Messages, etc.).*

---

## 📥 Installation Steps

Follow these steps to set up and run the bot locally or on a server:

### Prerequisites
* Python 3.9 or higher installed on your system.
* A Telegram Account.

### Step 1: Clone or Copy the Files
Ensure all files are placed in the project directory:
* `requirements.txt`
* `bot.py`
* `.env.example`

### Step 2: Set Up a Virtual Environment (Optional but Recommended)
Create and activate a virtual environment to manage dependencies cleanly:

**On Windows (Command Prompt/PowerShell):**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/activate
```

### Step 3: Install Dependencies
Install the required packages using pip:
```bash
pip install -r requirements.txt
```

### Step 4: Configure the Bot Token
1. Open Telegram and search for the `@BotFather`.
2. Send `/newbot` and follow the prompts to create your bot and obtain your **Bot API Token**.
3. Copy `.env.example` to a new file named `.env`:
   ```bash
   cp .env.example .env
   ```
4. Edit the `.env` file and replace `your_bot_token_here` with your actual token:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   ```

---

## 🚀 Running the Bot

Run the bot script using Python:
```bash
python bot.py
```
Upon startup, the bot will log initialization information and state:
`Background deletion scheduler initialized: running every 5 minutes (300s).`
`Bot started successfully. Waiting for messages...`

---

## 👥 Adding the Bot to a Group

1. Open your bot's profile in Telegram (either by searching for its username or clicking the link provided by `@BotFather`).
2. Click on the bot's description/profile header and select **Add to Group**.
3. Select the group you want the bot to manage.
4. Go to the Group Settings -> Administrators -> **Add Admin**, choose your bot, enable **Delete Messages**, and click **Save**.

---

## 💬 Bot Commands

* `/start` or `/help`  
  Sends a helpful user guide explaining the bot's purpose, setup steps, and available commands.
* `/setdelay <minutes>` (Group Administrators Only)  
  Updates the deletion delay configuration for the group. For example, `/setdelay 10` will delete stickers and GIFs 10 minutes after they are sent. 
  * Default: 5 minutes (300 seconds).
  * Maximum: 48 hours (2880 minutes) due to Telegram API limits.
  * If run without arguments, it displays the group's current delay configuration.
