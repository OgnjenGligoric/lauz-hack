import requests
import sys


BASE_URL = "http://localhost:5005"
ENDPOINT = "/" 

def send_coordinates(x_coord: int, y_coord: int):
    """
    Sends screen coordinates (x, y) to the IntelliJ plugin's HTTP server.
    """
    url = BASE_URL + ENDPOINT
    
    params = {
        'x': x_coord,
        'y': y_coord
    }
    
    print(f"✅ Attempting to send request to: {url} with params: {params}")

    try:
        
        response = requests.get(url, params=params, timeout=5)
        
        response.raise_for_status() 
        
        print("\n--- Server Response ---")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        print("-----------------------")
        
        if response.status_code == 200:
            print("\n🎉 Success! The plugin has received the coordinates and executed the action.")
        
    except requests.exceptions.RequestException as e:
        print("\n--- Request FAILED ---")
        if hasattr(e, 'response') and e.response is not None:
            print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
        else:
            print(f"Connection Error: Could not reach the server at {BASE_URL}. Ensure the plugin is running and port 5005 is open.")
            print(f"Details: {e}")
        print("----------------------")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python send_coords.py <screen_x_coordinate> <screen_y_coordinate>")
        print("Example: python send_coords.py 1920 540")
        sys.exit(1)

    try:
        x = int(sys.argv[1])
        y = int(sys.argv[2])
        send_coordinates(x, y)
    except ValueError:
        print("Error: Both coordinates must be valid integers.")
        sys.exit(1)