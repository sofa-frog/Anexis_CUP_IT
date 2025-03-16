import requests
import pandas as pd
import pytz
import heapq
from datetime import datetime
from tzlocal import get_localzone

# Конфигурация
API_KEY = "c206bef2-e21c-49ce-9689-88b5fe98e756"
LOCAL_TZ = get_localzone()

# Инициализация структур данных
cities_df = pd.DataFrame(columns=['city', 'departure_date', 'city_code'])
routes_df = pd.DataFrame(columns=['from', 'to', 'departure', 'local_departure', 'arrival', 'local_arrival',
                                  'duration', 'transport_type'])


def get_city_code(city_title):
    url = "https://api.rasp.yandex.net/v3.0/stations_list/"
    params = {"apikey": API_KEY, "lang": "ru_RU", "format": "json"}

    response = requests.get(url, params=params)
    response.raise_for_status()

    for country in response.json()["countries"]:
        for region in country["regions"]:
            for settlement in region["settlements"]:
                if settlement["title"] == city_title:
                    return settlement["codes"]["yandex_code"]
    raise ValueError(f"Город '{city_title}' не найден")


def get_city_name(code):
    """Безопасное получение названия города по коду"""
    city = cities_df[cities_df['city_code'] == code]['city']
    return city.values[0] if not city.empty else f"Город с кодом {code}"


def fetch_routes(from_code, to_code, date):
    url = "https://api.rasp.yandex.net/v3.0/search/"
    params = {
        "apikey": API_KEY,
        "from": from_code,
        "to": to_code,
        "date": date,
        "format": "json",
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get('segments', [])


def process_route(route, from_code, to_code):
    departure = datetime.fromisoformat(route['departure']).astimezone(pytz.UTC)
    arrival = datetime.fromisoformat(route['arrival']).astimezone(pytz.UTC)

    departure_local = datetime.fromisoformat(route['departure'])
    arrival_local = datetime.fromisoformat(route['arrival'])

    return {
        'from': from_code,
        'to': to_code,
        'departure': departure,
        'local_departure': departure_local,
        'arrival': arrival,
        'local_arrival': arrival_local,
        'duration': route['duration'],
        'transport_type': route['thread']['transport_type']
    }


def find_all_routes(start, end):
    """Поиск всех маршрутов с учетом возвратов и последовательности городов"""
    city_sequence = cities_df['city_code'].tolist()

    def dfs(current_index, path, current_time):
        # Базовый случай: достигли конца последовательности
        if current_index >= len(city_sequence) - 1:
            if city_sequence[-1] == end:
                return [{
                    'path': path.copy(),
                    'total_time': current_time,
                    'travel_time': sum(step['duration'] for step in path)
                }]
            return []

        current_city = city_sequence[current_index]
        next_city = city_sequence[current_index + 1]

        # Получаем разрешенные рейсы между текущим и следующим городом
        possible_routes = routes_df[
            (routes_df['from'] == current_city) &
            (routes_df['to'] == next_city) &
            (routes_df['departure'] >= cities_df.iloc[current_index]['departure_date'])
            ]

        results = []

        for _, route in possible_routes.iterrows():
            # Рассчитываем время ожидания
            wait_time = 0
            if path:
                prev_arrival = path[-1]['arrival']
                wait_time = (route['departure'] - prev_arrival).total_seconds()
                if wait_time < 0: continue

            new_step = {
                'from': current_city,
                'to': next_city,
                'departure': route['departure'],
                'local_departure': route['local_departure'],
                'arrival': route['arrival'],
                'local_arrival': route['local_arrival'],
                'transport': route['transport_type'],
                'duration': route['duration'],
                'waiting': wait_time
            }

            # Рекурсивный переход к следующему городу в последовательности
            results += dfs(
                current_index + 1,
                path + [new_step],
                current_time + route['duration'] + wait_time
            )

        return results

    return dfs(0, [], 0)


if __name__ == "__main__":
    start_city = input("Город отправления: ")
    end_city = input("Город прибытия: ")
    date = input("Введите дату отправления (YYYY-MM-DD): ")
    naive_date = datetime.strptime(date, "%Y-%m-%d")
    departure_datetime_utc = naive_date.replace(tzinfo=pytz.UTC)

    cities = [start_city, end_city]
    dates = [departure_datetime_utc]

    additional = int(input("Количество дополнительных остановок: "))
    for _ in range(additional):
        cities.insert(-1, input("Город остановки: "))
        date = input("Введите дату отправления (YYYY-MM-DD): ")
        naive_date = datetime.strptime(date, "%Y-%m-%d")
        departure_datetime_utc = naive_date.replace(tzinfo=pytz.UTC)
        dates.append(departure_datetime_utc)
    dates.append(departure_datetime_utc)

    filter = int(input(f"Поставьте - (1, 2, 3) если нужно отфильтировать данные"
                       f"(1 - по общему времени, 2 - по времени в пути, 3 - по обеим критиреям): "))

    for i in range(len(cities)):
        code = get_city_code(cities[i])
        new_row = pd.DataFrame([{'city': cities[i], 'city_code': code, 'departure_date': dates[i]}])
        cities_df = pd.concat([cities_df, new_row], ignore_index=True)

    for i in range(len(cities_df) - 1):
        from_code = cities_df.iloc[i]['city_code']
        to_code = cities_df.iloc[i + 1]['city_code']
        date_departure = cities_df.iloc[i]['departure_date']

        for route in fetch_routes(from_code, to_code, date_departure):
            processed = process_route(route, from_code, to_code)
            new_route = pd.DataFrame([processed])
            routes_df = pd.concat([routes_df, new_route], ignore_index=True)

    start_code = cities_df.iloc[0]['city_code']
    end_code = cities_df.iloc[-1]['city_code']

    #print(routes_df.to_string())

    # Вcе возможные пути
    all_routes = find_all_routes(start_code, end_code)

    if (filter == 1 or filter == 2 or filter == 3):
        if filter == 1:
            all_routes.sort(key=lambda x: x['total_time'])
        elif filter == 2:
            all_routes.sort(key=lambda x: x['travel_time'])
        else:
            all_routes.sort(key=lambda x: x['total_time'])
            all_routes.sort(key=lambda x: x['travel_time'])


    if all_routes:
        print(f"\nНайдено {len(all_routes)} маршрутов:")
        for i, route in enumerate(all_routes, 1):
            print(f"\nМаршрут #{i}:")
            print(f"Общее время: {route['total_time'] / 3600:.2f} ч")
            print(f"Чистое время в дороге: {route['travel_time'] / 3600:.2f} ч")
            for step in route['path']:
                print(f"  {get_city_name(step['from'])} -> {get_city_name(step['to'])}")
                print(f"  Транспорт: {step['transport']}")
                print(f"  Местное время отправление: {step['local_departure'].strftime('%Y-%m-%d %H:%M')}")
                print(f"  Местное время прибытие: {step['local_arrival'].strftime('%Y-%m-%d %H:%M')}")
                print(f"  В пути: {step['duration'] / 3600:.1f} ч")
                print(f"  Ожидание: {step['waiting'] / 3600:.1f} ч")
                print("-" * 40)
    else:
        print("Маршруты не найдены")