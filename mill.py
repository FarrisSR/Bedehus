import requests

# Globale konstanter
IP_ADDRESS = "192.168.0.173"
TEMP_TYPE = "Normal"

def set_temperature(value):
    """
    Setter temperaturen ved å sende en POST-forespørsel til /set-temperature.
    Her er TEMP_TYPE statisk, og kun temperaturen (value) varierer.
    """
    url = f"http://{IP_ADDRESS}/set-temperature"
    headers = {"Content-Type": "application/json"}
    payload = {"type": TEMP_TYPE, "value": value}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Hever exception hvis HTTP-koden ikke er 200-299
        return response.json()
    except requests.RequestException as error:
        print(f"Feil ved å sette temperatur: {error}")
        return None

def get_control_status():
    """
    Henter kontrollstatus ved å sende en GET-forespørsel til /control-status.
    Denne endepunktet krever ingen payload.
    """
    url = f"http://{IP_ADDRESS}/control-status"
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Sjekker om HTTP-koden indikerer feil
        return response.json()
    except requests.RequestException as error:
        print(f"Feil ved henting av kontrollstatus: {error}")
        return None

if __name__ == "__main__":
    # Eksempel på bruk:
    status_response = get_control_status()
    print("Respons fra get_control_status:", status_response)

    temperature_response = set_temperature(17)
    print("Respons fra set_temperature:", temperature_response)
    
    status_response = get_control_status()
    print("Respons fra get_control_status:", status_response)

