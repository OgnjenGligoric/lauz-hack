import requests
import sys

# ----------------------------------------------------
# Configuration
# ----------------------------------------------------
# Base URL for the Netty server running in the IntelliJ plugin sandbox
BASE_URL = "http://localhost:5005"
ENDPOINT = "/" 

def send_coordinates(x_coord: int, y_coord: int):
    """
    Sends screen coordinates (x, y) to the IntelliJ plugin's HTTP server.
    """
    url = BASE_URL + ENDPOINT
    
    # 1. Prepare the query parameters dictionary
    params = {
        'x': x_coord,
        'y': y_coord
    }
    
    print(f"✅ Attempting to send request to: {url} with params: {params}")

    try:
        # 2. Send the GET request with the parameters
        # requests automatically handles constructing the full URL: http://localhost:5005/?x=...&y=...
        response = requests.get(url, params=params, timeout=5)
        
        # 3. Check the response status code
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        
        # 4. Success handling
        print("\n--- Server Response ---")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        print("-----------------------")
        
        if response.status_code == 200:
            print("\n🎉 Success! The plugin has received the coordinates and executed the action.")
        
    except requests.exceptions.RequestException as e:
        # 5. Error handling
        print("\n--- Request FAILED ---")
        if hasattr(e, 'response') and e.response is not None:
            # Handle 400 Bad Request error returned by your Netty handler
            print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
        else:
            # Handle connection errors (e.g., server not running, connection refused)
            print(f"Connection Error: Could not reach the server at {BASE_URL}. Ensure the plugin is running and port 5005 is open.")
            print(f"Details: {e}")
        print("----------------------")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        # Display usage instructions if not enough arguments are provided
        print("Usage: python send_coords.py <screen_x_coordinate> <screen_y_coordinate>")
        print("Example: python send_coords.py 1920 540")
        sys.exit(1)

    try:
        # Get coordinates from command line arguments
        x = int(sys.argv[1])
        y = int(sys.argv[2])
        send_coordinates(x, y)
    except ValueError:
        print("Error: Both coordinates must be valid integers.")
        sys.exit(1)