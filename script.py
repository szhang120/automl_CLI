def strcspn(word, ch):
    for i, c in enumerate(word):
        if c == ch:
            return i
    return len(word)

def find_trigger_char(words, target=25):
    from string import ascii_lowercase
    for ch in ascii_lowercase:
        total = sum(strcspn(w, ch) for w in words)
        if total == target:
            return ch
    return None

words = [
    "though", "spurted", "reneger", "zaxes", "timelier", "bronzier", "rupees", "triazole",
    "pencels", "meshier", "culverts", "flossed", "wartless", "yuckiest", "manacle",
    "fellated", "hadarim", "externe", "hempseed", "glisten", "eolopile", "newsy", "aliyahs",
    "amide", "fattest", "kohl", "burling", "rodlike", "refuge", "brassie", "toplofty",
    "unarmed"
]

result = find_trigger_char(words)
print(result)
