# Telegram Ad Bot

This Telegram bot links advertisers with channel owners. It places ads without manual work. Developers wrote the code in a clear, easy-to-change way.

## 🚀 Features

*   **User Registration**: Sign up as an advertiser or a channel owner.
*   **Campaign Management**: Create, manage, and track your ad campaigns.
*   **Channel Verification**: The bot checks channels and finishes setup on its own.
*   **Ad Automation**: The bot posts and handles ads for you.
*   **Balance System**: Track your funds with a virtual currency.
*   **Notifications**: Receive quick updates on campaign status.

## 🏗️ Architecture

The project groups code into folders. Each folder does one main task.

```
telegram_ad_bot/
├── config/              # Configuration management
│   ├── settings.py      # Application settings
│   └── logging.py       # Logging configuration
├── database/            # Database layer
│   ├── connection.py    # Database connection
│   └── migrations.py    # Database migrations
├── handlers/            # Telegram bot handlers
│   ├── registration_handlers.py  # User/channel registration
│   ├── campaign_handlers.py      # Campaign management
│   ├── bot_handlers.py          # Core menu handlers
│   ├── helpers.py               # Reusable UI components
│   ├── error_handlers.py        # Centralized error handling
│   └── states.py               # FSM states
├── models/              # Data models
│   ├── user.py         # User model
│   ├── campaign.py     # Campaign model
│   ├── channel.py      # Channel model
│   └── transaction.py  # Transaction model
├── services/            # Business logic services
│   ├── user_service.py        # User management
│   ├── campaign_service.py    # Campaign operations
│   ├── channel_service.py     # Channel management
│   ├── notification_service.py # Notifications
│   ├── posting_service.py     # Ad posting
│   ├── verification_service.py # Channel verification
│   └── escrow_service.py      # Payment handling
└── main.py             # Application entry point
```

## 🛠️ Setup

### Prerequisites

*   Python 3.8 or higher.
*   Telegram Bot Token from [@BotFather](https://t.me/BotFather).

### Installation

1.  Clone the repository.
    ```bash
    git clone https://github.com/mentariochain1/telegram_ad_bot.git
    cd telegram_ad_bot
    ```

2.  Create a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  Install dependencies.
    ```bash
    pip install -r requirements.txt
    ```

4.  Set up your environment.
    ```bash
    cp .env.example .env
    # Edit .env with your configuration
    ```

5.  Set up the database.
    ```bash
    python -m telegram_ad_bot.database.migrations
    ```

6.  Start the bot.
    ```bash
    python main.py
    ```

## ⚙️ Configuration

Set these environment variables in your .env file.

| Variable | Description | Default |
|----------|-------------|---------|
| BOT_TOKEN | Telegram bot token from @BotFather | Required |
| DATABASE_URL | Database connection string | sqlite+aiosqlite:///./telegram_ad_bot.db |
| LOG_LEVEL | Logging level: DEBUG, INFO, WARNING, ERROR | INFO |
| LOG_FILE | Log file path, if you want one | None |
| ENVIRONMENT | development or production | development |
| DEBUG | Turn on debug mode | false |
| DEFAULT_CAMPAIGN_DURATION_HOURS | Hours for default campaigns | 1 |

## 🧪 Development

### Code Quality

The code meets clear standards. We separate code by function. Each module handles one job. We use helper functions to avoid repeats. Functions stay short, under 30 lines. Type hints make code clear. One system catches all errors. Docstrings explain the code in detail.

### Running Tests

Install test packages.
```bash
pip install -r requirements.txt
```

Run the tests.
```bash
pytest
```

Run tests with coverage.
```bash
pytest --cov=telegram_ad_bot
```

### Code Formatting

Format the code.
```bash
black telegram_ad_bot/
```

Check for style issues.
```bash
flake8 telegram_ad_bot/
```

Check types.
```bash
mypy telegram_ad_bot/
```

## 📝 Usage

1.  Start the bot. Send /start to it.
2.  Choose your role. Pick advertiser or channel owner.
3.  For advertisers:
    *   Create campaigns. Add ad text and budget.
    *   Track status.
    *   Manage your balance.
4.  For channel owners:
    *   Register channels. Verify them.
    *   View campaigns.
    *   Accept them and earn money.

## 🔧 Update Notes

We fixed the code recently. Long functions split into shorter ones. Functions of 95 lines became 15 to 25 lines. Repeated code moved to helpers. Modules now focus on single tasks. Errors go to one handler with clear messages. The structure improved. Code size dropped by 30 percent. Maintenance got easier.

## 🤝 Contributing

1.  Fork the repository.
2.  Create a feature branch. Use git checkout -b feature/amazing-feature.
3.  Commit your changes. Use git commit -m 'Add amazing feature'.
4.  Push to the branch. Use git push origin feature/amazing-feature.
5.  Open a Pull Request.

## 📄 License

This project uses the MIT License. Check the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

*   The project builds on [aiogram](https://github.com/aiogram/aiogram). This framework handles Telegram bots.