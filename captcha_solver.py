import json
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class CaptchaSolver:
    def __init__(self, headless=False):
        """Initialize the CaptchaSolver with browser options."""
        self.headless = headless
        self.driver = None


    def initialize_driver(self):
        """Initialize Chrome driver with optimized settings"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")

        # Disable USB device logging
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def prepare_input_field(self, element):
        """Make sure the input field is ready for interaction"""
        try:
            self.driver.execute_script("""
                const input = arguments[0];
                input.style.opacity = 1;
                input.style.visibility = 'visible';
                input.style.display = 'block';
                input.removeAttribute('disabled');
                input.removeAttribute('readonly');
                input.classList.remove('entry-disabled');
                input.scrollIntoView({behavior: 'smooth', block: 'center'});
            """, element)
            time.sleep(0.3)  # Allow for transitions
        except Exception as e:
            print(f"Warning: Could not fully prepare input field: {e}")

    def enter_email(self, element, email):
        """Robust email entry with multiple fallbacks"""
        try:
            # First try standard Selenium method
            element.clear()
            element.send_keys(email)
            print("Email entered via standard Selenium method")
        except WebDriverException:
            try:
                # Fallback to JavaScript with focus
                self.driver.execute_script("""
                    arguments[0].focus();
                    arguments[0].value = arguments[1];
                    // Trigger change events
                    const event = new Event('input', { bubbles: true });
                    arguments[0].dispatchEvent(event);
                """, element, email)
                print("Email entered via JavaScript with focus")
            except Exception as e:
                print(f"Critical: Could not enter email: {e}")
                raise

    def find_real_input_field(self):
        """Enhanced method to find the real input field"""
        try:
            # JavaScript to find the most likely real input field
            js = """
               // Get all input fields
               const inputs = Array.from(document.querySelectorAll('input.form-control'));

               // Score inputs based on various factors
               const scoredInputs = inputs.map(input => {
                   let score = 0;

                   // Check z-index hierarchy
                   let element = input;
                   while (element) {
                       const zIndex = parseInt(window.getComputedStyle(element).zIndex) || 0;
                       if (zIndex > 0) score += zIndex;
                       element = element.parentElement;
                   }

                   // Check visibility and size
                   const rect = input.getBoundingClientRect();
                   if (rect.width > 0 && rect.height > 0) score += 100;

                   // Check if it's the first email field
                   if (input.getAttribute('id')?.toLowerCase().includes('email')) score += 50;

                   return {element: input, score: score};
               });

               // Sort by score and return the highest
               scoredInputs.sort((a, b) => b.score - a.score);
               return scoredInputs[0]?.element || null;
               """

            return self.driver.execute_script(js)
        except Exception as e:
            print(f"Error finding input field: {e}")
            return None

    def login(self, url, email):
        """Complete login process"""
        try:
            self.initialize_driver()
            self.driver.get(url)
            time.sleep(2)  # Initial page load

            # Find and prepare input field
            email_input = self.find_real_input_field()
            if not email_input:
                raise Exception("Could not find email input field")

            self.prepare_input_field(email_input)
            self.enter_email(email_input, email)

            # Click verify button
            verify_button = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "btnVerify")))
            self.driver.execute_script("arguments[0].click();", verify_button)
            print("Verify button clicked")

            # Wait for navigation
            time.sleep(3)
            print("Login process completed")

            return True

        except Exception as e:
            print(f"Login failed: {e}")
            if self.driver:
                self.driver.save_screenshot("login_error.png")
            return False


    def solve_captcha(self):
        driver = self.driver
        """Solve the CAPTCHA if it appears."""
        try:
            # Wait for CAPTCHA to load (if present)
            try:
                captcha_div = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "captcha-main-div"))
                )
                print("CAPTCHA detected, solving...")

                # Extract the number to find from the label
                number_to_find = self.get_number_to_find(driver)
                if not number_to_find:
                    print("Could not determine which number to find.")
                    return False

                print(f"Need to find boxes with number: {number_to_find}")

                # Take screenshot of the CAPTCHA area
                captcha_area = driver.find_element(By.CLASS_NAME, "p-3.row.no-gutters")
                screenshot = self.take_element_screenshot(driver, captcha_area)

                # Send to LLM for analysis (if API key available)
                if GEMINI_API_KEY:
                    captcha_cells = self.analyze_captcha_with_llm(screenshot, number_to_find)
                    if captcha_cells:
                        # Click on the identified cells
                        for cell_id in captcha_cells:
                            try:
                                cell = driver.find_element(By.ID, cell_id)
                                driver.execute_script("arguments[0].click();", cell)
                                time.sleep(0.5)
                            except NoSuchElementException:
                                print(f"Cell with ID {cell_id} not found.")

                # Submit the form again
                verify_button = driver.find_element(By.ID, "btnVerify")
                driver.execute_script("arguments[0].click();", verify_button)

                # Wait for redirection
                time.sleep(5)
                return True

            except TimeoutException:
                print("No CAPTCHA detected, proceeding...")
                return True

        except Exception as e:
            print(f"Error solving CAPTCHA: {e}")
            return False

    def get_number_to_find(self, driver):
        """Extract the target number from the CAPTCHA instruction."""
        try:
            script = """
            const labels = Array.from(document.querySelectorAll('.box-label'));
            const visibleLabels = labels.filter(el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                       rect.width > 0 && rect.height > 0;
            });
            visibleLabels.sort((a, b) => {
                const zA = parseInt(window.getComputedStyle(a).zIndex) || 0;
                const zB = parseInt(window.getComputedStyle(b).zIndex) || 0;
                return zB - zA;  // Descending
            });
            const topLabel = visibleLabels[0];
            return topLabel ? topLabel.innerText : null;
            """
            text = driver.execute_script(script)
            if text and "Please select all boxes with number" in text:
                return text.split("number")[1].strip()
            return None
        except Exception as e:
            print(f"Error extracting number to find: {e}")
            return None

    def take_element_screenshot(self, driver, element):
        """Take a screenshot of a specific element."""
        from PIL import Image
        from io import BytesIO
        import base64

        # Scroll element into view
        driver.execute_script("arguments[0].scrollIntoView();", element)
        time.sleep(0.5)

        # Take screenshot of the entire page
        screenshot = driver.get_screenshot_as_png()
        img = Image.open(BytesIO(screenshot))

        # Get element location and size
        location = element.location
        size = element.size

        # Calculate coordinates
        left = location['x']
        top = location['y']
        right = location['x'] + size['width']
        bottom = location['y'] + size['height']

        # Crop the image
        img = img.crop((left, top, right, bottom))

        # Convert to base64 for API transmission
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

    def get_visible_instruction(self):
        """Get the currently visible instruction text using JavaScript"""
        script = """
        // Get all instruction elements
        const labels = Array.from(document.querySelectorAll('.box-label'));

        // Find the visible one (not hidden by CSS)
        const visibleLabel = labels.find(el => {
            const style = window.getComputedStyle(el);
            return style.display !== 'none' && 
                   style.visibility !== 'hidden' &&
                   el.offsetWidth > 0 && 
                   el.offsetHeight > 0;
        });

        // Extract the number if found
        if (visibleLabel && visibleLabel.textContent.includes('number')) {
            return visibleLabel.textContent.split('number')[1].trim();
        }
        return null;
        """
        return self.driver.execute_script(script)

    def solve_captcha(self):
        """Solve the CAPTCHA if it appears."""
        try:
            # Wait for CAPTCHA to load (if present)
            try:
                captcha_div = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "captcha-main-div"))
                )
                print("CAPTCHA detected, solving...")

                # Extract the visible instruction text
                number_to_find = self.get_visible_instruction()
                if not number_to_find:
                    print("Could not determine which number to find.")
                    return False

                print(f"Need to find boxes with number: {number_to_find}")

                # Take screenshot of the entire CAPTCHA area
                captcha_area = self.driver.find_element(By.CLASS_NAME, "main-div-container")
                screenshot = self.take_element_screenshot(self.driver, captcha_area)

                # Get positions of all visible boxes
                visible_boxes = self.get_visible_boxes()

                # Send to LLM for analysis
                if GEMINI_API_KEY:
                    # Get click coordinates from AI
                    click_coordinates = self.analyze_captcha_with_llm(
                        screenshot,
                        number_to_find,
                        captcha_area.location,
                        captcha_area.size
                    )

                    if click_coordinates:
                        # Click on the identified coordinates
                        for coord in click_coordinates:
                            self.click_at_coordinate(coord['x'], coord['y'])
                            time.sleep(0.5)

                # Submit the form again
                verify_button = self.driver.find_element(By.ID, "btnVerify")
                self.driver.execute_script("arguments[0].click();", verify_button)

                # Wait for redirection
                time.sleep(5)
                return True

            except TimeoutException:
                print("No CAPTCHA detected, proceeding...")
                return True

        except Exception as e:
            print(f"Error solving CAPTCHA: {e}")
            return False

    def get_visible_boxes(self):
        """Get all actually visible CAPTCHA boxes with their positions and sizes"""
        script = """
        // Get all CAPTCHA box containers
        const boxes = Array.from(document.querySelectorAll('.p-3.row.no-gutters > div'));

        // Filter visible boxes and get their positions
        return boxes.filter(box => {
            const style = window.getComputedStyle(box);
            return style.display !== 'none' && 
                   style.visibility !== 'hidden' &&
                   box.offsetWidth > 0 && 
                   box.offsetHeight > 0;
        }).map(box => {
            const rect = box.getBoundingClientRect();
            return {
                id: box.id,
                x: rect.left + window.scrollX,
                y: rect.top + window.scrollY,
                width: rect.width,
                height: rect.height,
                centerX: rect.left + window.scrollX + (rect.width / 2),
                centerY: rect.top + window.scrollY + (rect.height / 2)
            };
        });
        """
        return self.driver.execute_script(script)

    def click_at_coordinate(self, x, y):
        """Click at a specific coordinate on the page"""
        self.driver.execute_script(f"""
            const ev = new MouseEvent('click', {{
                view: window,
                bubbles: true,
                cancelable: true,
                clientX: {x},
                clientY: {y}
            }});
            document.elementFromPoint({x}, {y}).dispatchEvent(ev);
        """)

    def analyze_captcha_with_llm(self, screenshot_base64, number_to_find, area_location, area_size):
        """Send the CAPTCHA screenshot to Gemini API for coordinate-based analysis."""
        try:
            import requests

            if not GEMINI_API_KEY:
                print("No Gemini API key available, skipping LLM analysis")
                return []

            # Prepare the prompt with clear instructions
            prompt = f"""
            Analyze this CAPTCHA image showing boxes containing numbers. 
            Some boxes contain the number {number_to_find}.

            Instructions:
            1. Identify all boxes that clearly show the number {number_to_find}
            2. For each matching box, determine the center coordinates (x,y) where:
               - (0,0) is the top-left corner of the CAPTCHA area
               - x increases to the right
               - y increases downward
            3. Return ONLY the coordinates as a JSON list like:
               [{{"x":100,"y":50}}, {{"x":200,"y":150}}]

            Important:
            - Only include boxes where the number is clearly visible
            - Coordinates should be relative to the CAPTCHA area, not the whole page
            - If no boxes contain the number, return an empty list
            - Do not include any other text in your response
            """

            # API endpoint
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

            # Prepare request payload
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": screenshot_base64
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "response_mime_type": "application/json"
                }
            }

            # Send request
            response = requests.post(url, json=payload)
            response_data = response.json()

            # Parse the response
            try:
                text_response = response_data['candidates'][0]['content']['parts'][0]['text']
                # Parse the JSON response
                coordinates = json.loads(text_response)

                # Convert coordinates from CAPTCHA-relative to page-absolute
                for coord in coordinates:
                    coord['x'] += area_location['x']
                    coord['y'] += area_location['y']

                return coordinates
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                print(f"Error parsing API response: {e}")
                return []

        except Exception as e:
            print(f"Error analyzing CAPTCHA with LLM: {e}")
            return []

    def close(self, driver):
        """Close the browser."""
        if driver:
            driver.quit()


# Example usage
if __name__ == "__main__":
    LOGIN_URL = "https://ita-pak.blsinternational.com/Global/account/login"
    EMAIL = "abdulmannankhan1000@gmail.com"

    # Initialize and run the CAPTCHA solver
    solver = CaptchaSolver(headless=False)
    driver = None
    try:
        solver.login(LOGIN_URL, EMAIL)
        solver.solve_captcha()
    except Exception as e:
        print(e)
