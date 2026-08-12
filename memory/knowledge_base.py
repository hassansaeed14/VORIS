from memory.memory_manager import remember, recall

def store_user_name(name):
    remember("user_name", name)

def get_user_name():
    return recall("user_name")

def store_info(key, value):
    remember(key, value)

def get_info(key):
    return recall(key)

def store_user_age(age):
    remember("user_age", age)

def get_user_age():
    return recall("user_age")

def store_user_city(city):
    remember("user_city", city)

def get_user_city():
    return recall("user_city")