from cryptography.fernet import Fernet

key = Fernet.generate_key()
print(key)  # Cela vous donnera la clé à utiliser dans votre application
