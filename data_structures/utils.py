import string


TITLES = ["mr", "ms", "mrs", "dr", "rev"]
SUFFIXES = ["jr", "sr", "iii"]

def pop_from_name(name, candidates):
    parts = name.split()
    for cand in candidates:
        for i, p in enumerate(parts):
            if cand == p.lower().strip(string.whitespace+string.punctuation):
                return cand, name.replace(p, "")
    return None, name

def pop_title(name):
    return pop_from_name(name, TITLES)

def pop_suffix(name):
    return pop_from_name(name, SUFFIXES)


def get_name_parts(name):
    title, name = pop_title(name)
    suffix, name = pop_suffix(name)
    parts_dict = {"title": title, "suffix": suffix}

    parts = name.split(',')
    if len(parts) > 1:
        # last, first m format
        parts_dict["last"] = parts[0]
        first_m = parts[1]
        parts = first_m.split()
        parts_dict["first"] = parts[0]
        if len(parts) > 1:
            parts_dict["middle"] = parts[1]
    else:
        # first m last format
        parts_dict["first"] = parts[0]
        parts_dict["last"] = parts[-1]
        if len(parts) == 3:
            parts_dict["middle"] = parts[1]
    return parts_dict


