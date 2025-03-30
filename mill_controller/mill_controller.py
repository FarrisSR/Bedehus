import requests


class mill_controller:
    def __init__(self, ip_address, temp_type="Normal"):
        self.ip_address = ip_address
        self.temp_type = temp_type

    def set_temperature(self, value):
        """
        Setter temperaturen ved å sende en POST-forespørsel til /set-temperature.
        """
        url = f"http://{self.ip_address}/set-temperature"
        headers = {"Content-Type": "application/json"}
        payload = {"type": self.temp_type, "value": value}

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()  # Hever exception hvis HTTP-koden ikke er 200-299
            return response.json()
        except requests.RequestException as error:
            print(f"Feil ved å sette temperatur: {error}")
            return None

    def get_control_status(self):
        """
        Henter kontrollstatus ved å sende en GET-forespørsel til /control-status.
        """
        url = f"http://{self.ip_address}/control-status"

        try:
            response = requests.get(url)
            response.raise_for_status()  # Sjekker om HTTP-koden indikerer feil
            return response.json()
        except requests.RequestException as error:
            print(f"Feil ved henting av kontrollstatus: {error}")
            return None


# Eksempel på bruk:
if __name__ == "__main__":
    # Du kan lese IP-adressen fra en konfigurasjonsfil, miljøvariabel, eller bruke input fra brukeren.
    ip_config = input("Skriv inn IP-adresse for kontrolleren: ")
    controller = mill_controller(ip_address=ip_config)

    result = controller.set_temperature(22)
    print("Svar ved endring av temperatur:", result)

    status = controller.get_control_status()
    print("Kontrollstatus:", status)
