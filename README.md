# Telegram Coupon Bot - Complete Auto-Delivery System

A production-ready Telegram bot for selling digital coupons with automatic code delivery after admin approval.

## Features

### User Features
- Browse available coupons
- Buy coupons with UPI payment
- Submit UTR for verification
- Automatic code delivery after approval
- Order tracking
- Order history

### Admin Features
- Add coupons
- Bulk add coupon codes
- Approve/reject orders with automatic code delivery
- Stock management
- Low stock alerts
- Broadcast messages
- View statistics
- Change UPI settings

### Automated System
- Automatically fetches unused codes from database
- Marks codes as used after delivery
- Instantly delivers codes to user after approval
- Prevents approval if insufficient codes
- Low stock warnings
- Duplicate UTR prevention

## Installation

### Prerequisites
- Python 3.11 or higher
- Telegram Bot Token (from @BotFather)
- Admin Telegram ID

### Local Setup

1. **Clone the repository:** ```bash
git clone https://github.com/yourusername/telegram-coupon-bot.git
cd telegram-coupon-bot
