from urllib.parse import quote
import requests
from PIL import Image
import os


class ImageGenerator:
    def __init__(self):
        self.image_api = "https://image.pollinations.ai/prompt/"

    def generate(self, prompt: str, filename: str) -> str:
        """
        Генерирует изображение на основе промпта и сохраняет его в файл.
        Использует модель Flux для генерации изображений.
        
        Args:
            prompt: Текстовое описание для генерации изображения
            filename: Путь к файлу для сохранения изображения
            
        Returns:
            str: Путь к сохраненному файлу
        """
        # Добавляем модель Flux через параметр model
        encoded_prompt = quote(prompt, safe="")
        url = f"{self.image_api}{encoded_prompt}?model=flux"
        
        print(f"🌐 Запрос к Pollination API: {url[:150]}...")
        resp = requests.get(url, timeout=60)  # Увеличиваем timeout до 60 секунд
        
        # Проверяем статус ответа
        if resp.status_code != 200:
            raise Exception(f"Pollination API вернул статус {resp.status_code}: {resp.text[:200]}")
        
        # Проверяем, что ответ - это изображение
        if not resp.content or len(resp.content) < 1000:  # Изображение должно быть больше 1KB
            raise Exception(f"Получен неверный ответ от API (размер: {len(resp.content)} байт)")
        
        # Создаем директорию для временных изображений, если её нет
        os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
        
        # Сохраняем изображение
        with open(filename, "wb") as f:
            f.write(resp.content)
        
        print(f"📥 Изображение загружено ({len(resp.content)} байт)")
        
        # Обрезаем водяной знак внизу (60 пикселей)
        try:
            with Image.open(filename) as img:
                width, height = img.size
                new_height = height - 60
                if new_height > 0:
                    cropped = img.crop((0, 0, width, new_height))
                    cropped.save(filename)
                    print(f"✂️ Изображение обрезано: {width}x{new_height}")
                else:
                    print(f"⚠️ Высота изображения слишком мала для обрезки: {height}")
        except Exception as e:
            print(f"⚠️ Ошибка при обрезке изображения: {e}")
            # Продолжаем работу, даже если обрезка не удалась
        
        return filename

