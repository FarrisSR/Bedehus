from yr.libyr import Yr

weather = Yr(location_name='Norge/Telemark/Skien/Skien')
now = weather.now(as_json=True)

print(now)
