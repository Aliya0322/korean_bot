# Инструкция по обновлению проекта на сервере

## 1. Подключитесь к серверу через SSH
```bash
ssh root@your-server-ip
```

## 2. Перейдите в директорию проекта
```bash
cd ~/TelegramBot/KoreanBot
```

## 3. Остановите бота (если запущен)
```bash
pkill -f "Telegram_Korean.py"
# или
ps aux | grep Telegram_Korean
kill <PID>
```

## 4. Проверьте статус git репозитория
```bash
git status
```

## 5. Сохраните локальные изменения (если есть)
```bash
# Если есть незакоммиченные изменения, которые нужно сохранить:
git stash

# Или отменить локальные изменения:
git reset --hard
```

## 6. Получите обновления из GitHub
```bash
git fetch origin
git pull origin main
```

## 7. Обновите зависимости (если requirements.txt изменился)
```bash
pip install -r requirements.txt --upgrade
```

## 8. Проверьте .env файл (убедитесь, что все переменные на месте)
```bash
cat .env
# Убедитесь, что все необходимые переменные присутствуют
```

## 9. Запустите бота снова
```bash
# В фоновом режиме:
nohup python3 Telegram_Korean.py > bot.log 2>&1 &

# Или с screen/tmux:
screen -S korean_bot
python3 Telegram_Korean.py
# Ctrl+A, затем D для отсоединения
```

## 10. Проверьте, что бот запустился
```bash
ps aux | grep Telegram_Korean
tail -f bot.log  # для просмотра логов
```

## Быстрая команда (все в одном):
```bash
cd ~/TelegramBot/KoreanBot && \
pkill -f "Telegram_Korean.py" && \
git pull origin main && \
pip install -r requirements.txt --upgrade && \
nohup python3 Telegram_Korean.py > bot.log 2>&1 &
```
