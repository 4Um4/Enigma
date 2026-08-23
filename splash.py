"""
Назначение: окно загрузки при ожидании загрузки backend
"""

import os
import sys
import time
import urllib.request
import tkinter as tk
from tkinter import font as tkfont

class SplashScreen(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bloodloom")
        self.geometry("720x400")
        self.configure(bg="#0F1419")
        self.overrideredirect(True)  # Убираем рамки окна
        
        # Центрирование
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (720 // 2)
        y = (screen_height // 2) - (400 // 2)
        self.geometry(f"720x400+{x}+{y}")

        # Стиль
        accent_color = "#00A887"
        text_color = "#FFFFFF"
        bg_card = "#1A2332"

        # Логотип / Заголовок
        title_font = tkfont.Font(family="Segoe UI", size=32, weight="bold")
        self.label = tk.Label(self, text="BLOODLOOM", font=title_font, bg="#0F1419", fg=accent_color)
        self.label.pack(pady=(100, 20))

        # Статус
        status_font = tkfont.Font(family="Segoe UI", size=12)
        self.status_var = tk.StringVar()
        self.status_var.set("Инициализация движка...")
        self.status_label = tk.Label(self, textvariable=self.status_var, font=status_font, bg="#0F1419", fg=text_color)
        self.status_label.pack(pady=10)

        # Прогресс-бар (имитация)
        self.canvas = tk.Canvas(self, width=400, height=12, bg=bg_card, highlightthickness=0)
        self.canvas.pack(pady=20)
        self.progress_rect = self.canvas.create_rectangle(0, 0, 0, 12, fill=accent_color, outline="")
        
        # Анимация пульсации
        self._progress = 0
        self._direction = 1

        # Таймаут: если бэкенд не ответит за 60 секунд, закрываемся
        self._start_time = time.time()
        self._timeout = 60
        
        # Запуск проверки бэкенда
        self.after(100, self.update_progress)
        self.after(500, self.check_backend)

    def update_progress(self):
        # Простая анимация туда-сюда, пока бэкенд грузится
        self._progress += self._direction * 5
        if self._progress > 400:
            self._progress = 400
            self._direction = -1
        elif self._progress < 0:
            self._progress = 0
            self._direction = 1
            
        self.canvas.coords(self.progress_rect, 0, 0, self._progress, 12)
        self.after(50, self.update_progress)

    def check_backend(self):
        try:
            # Проверяем health endpoint бэкенда
            req = urllib.request.Request("http://localhost:8000/api/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    self.status_var.set("Готово!")
                    self.update()
                    self.after(500, self.destroy) # Закрываем splash
                    return
        except Exception:
            # Меняем текст, чтобы пользователь видел, что процесс идет
            if "AI" in self.status_var.get():
                self.status_var.set("Загрузка AI-модели в видеопамять...")
            else:
                self.status_var.set("Запуск игрового сервера...")
            
            # Проверка таймаута для защиты от зомби-процесса
            if time.time() - self._start_time > self._timeout:
                self.status_var.set("Ошибка: сервер не отвечает. Проверьте launch_error.log.")
                self.update()
                self.after(3000, self.destroy)
                return
                
        self.after(1000, self.check_backend)

if __name__ == "__main__":
    app = SplashScreen()
    app.mainloop()