conversation = []

def add(role, content):
    conversation.append({
        "role": role,
        "content": content
    })

def history():
    return conversation[-10:]