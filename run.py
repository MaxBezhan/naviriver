#!/usr/bin/env python3
"""Точка входу для запуску додатку"""
import os
import sys
from app import create_app

# Додаємо поточну папку в шлях
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = create_app(config_name='development')

if __name__ == '__main__':
    # Для розробки використовуємо вбудований сервер
    app.run(host='0.0.0.0', port=5000, debug=True)
