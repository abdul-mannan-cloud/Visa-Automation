from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

site = "https://ita-pak.blsinternational.com/Global/account/login"
email = "abdulmannankhan1000@gmail.com"

driver = webdriver.Chrome()
driver.get(site)
driver.maximize_window()

# Wait until the email label is present
wait = WebDriverWait(driver, 1000)
time.sleep(5)
email_label = wait.until(EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Email')]")))

# Get the input that follows the label
email_input = email_label.find_element(By.XPATH, "following-sibling::input")

# Optional: remove disabled class via JS if needed
driver.execute_script("arguments[0].classList.remove('entry-disabled')", email_input)
driver.execute_script("arguments[0].removeAttribute('disabled')", email_input)

# Send keys
email_input.send_keys(email)

# Click the Verify button
verify_button = wait.until(EC.element_to_be_clickable((By.ID, "btnVerify")))
verify_button.click()

time.sleep(5)
# driver.quit()  # Uncomment to close browser
