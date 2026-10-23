import requests
import json

def get_moscow_weather():
    latitude = 55.7522
    longitude = 37.6156
    timezone = "Europe/Moscow"
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code&daily=temperature_2m_max,temperature_2m_min,weather_code,sunrise,sunset&current=temperature_2m,weather_code,wind_speed_10m,wind_direction_10m&timezone={timezone}"
    )

    response = requests.get(url)
    response.raise_for_status()  # Raise an exception for HTTP errors
    data = response.json()

    current = data["current"]
    hourly = data["hourly"]
    daily = data["daily"]

    # WMO Weather codes mapping (simplified for brevity)
    weather_codes = {
        0: "Ясное небо",
        1: "В основном ясно",
        2: "Переменная облачность",
        3: "Пасмурно",
        45: "Туман",
        48: "Изморозь",
        51: "Легкая изморозь",
        53: "Умеренная изморозь",
        55: "Плотная изморозь",
        56: "Ледяная изморозь",
        57: "Плотная ледяная изморозь",
        61: "Слабый дождь",
        63: "Умеренный дождь",
        65: "Сильный дождь",
        66: "Ледяной дождь",
        67: "Сильный ледяной дождь",
        71: "Слабый снегопад",
        73: "Умеренный снегопад",
        75: "Сильный снегопад",
        77: "Снежные зерна",
        80: "Слабый ливень",
        81: "Умеренный ливень",
        82: "Сильный ливень",
        85: "Слабый снегопад", # Snow showers
        86: "Сильный снегопад", # Heavy snow showers
        95: "Гроза",
        96: "Гроза с градом",
        99: "Гроза с сильным градом",
    }

    # Extract current conditions
    current_temp = current["temperature_2m"]
    current_weather_code = current["weather_code"]
    current_wind_speed = current["wind_speed_10m"]
    current_wind_direction = current["wind_direction_10m"]
    current_weather_description = weather_codes.get(current_weather_code, "Неизвестно")

    # Extract daily forecast for today
    today_max_temp = daily["temperature_2m_max"][0]
    today_min_temp = daily["temperature_2m_min"][0]
    today_weather_code = daily["weather_code"][0]
    today_sunrise = daily["sunrise"][0]
    today_sunset = daily["sunset"][0]
    today_weather_description = weather_codes.get(today_weather_code, "Неизвестно")

    report = f"Ежедневная сводка погоды для Москвы:\n\n"
    report += f"Текущие условия:\n"
    report += f"  Температура: {current_temp}°C\n"
    report += f"  Погода: {current_weather_description}\n"
    report += f"  Ветер: {current_wind_speed} км/ч, {current_wind_direction}°\n\n"

    report += f"Прогноз на сегодня:\n"
    report += f"  Максимальная температура: {today_max_temp}°C\n"
    report += f"  Минимальная температура: {today_min_temp}°C\n"
    report += f"  Погода: {today_weather_description}\n"
    report += f"  Восход солнца: {today_sunrise.split('T')[1]} Заход солнца: {today_sunset.split('T')[1]}\n\n"

    # Recommendations based on weather
    recommendations = []
    if current_temp < 0 or today_min_temp < 0:
        recommendations.append("Одевайтесь теплее, возможен мороз.")
    elif current_temp > 25 or today_max_temp > 25:
        recommendations.append("Будет жарко, не забывайте о головном уборе и пейте больше воды.")

    if 61 <= current_weather_code <= 67 or 61 <= today_weather_code <= 67 or \
       80 <= current_weather_code <= 82 or 80 <= today_weather_code <= 82:
        recommendations.append("Возможен дождь, возьмите зонт.")

    if 71 <= current_weather_code <= 77 or 85 <= current_weather_code <= 86 or \
       71 <= today_weather_code <= 77 or 85 <= today_weather_code <= 86:
        recommendations.append("Возможен снегопад, будьте осторожны на дорогах.")

    if current_wind_speed > 20:
        recommendations.append("Ожидается сильный ветер, будьте внимательны.")

    if recommendations:
        report += "Рекомендации:\n" + "\n".join([f"  - {rec}" for rec in recommendations])
    else:
        report += "Рекомендации: Сегодня ожидается комфортная погода.\n"

    return report
