import random
from yafs.application import Message

BYTES_MAX = 2000
BYTES_MIN = 1000
INSTRUCTIONS_MAX = 500 * 10**6
INSTRUCTIONS_MIN = 200 * 10**6

class MessageProfile:
    class Request:
        name = "M_Req"
        instructions = (INSTRUCTIONS_MIN, INSTRUCTIONS_MAX)
        bytes = (BYTES_MIN, BYTES_MAX)
    
    class Response:
        name = "M_Resp"
        instructions = (INSTRUCTIONS_MIN, INSTRUCTIONS_MAX)
        bytes = (BYTES_MIN, BYTES_MAX)

class RandomMessage(Message):
    def __init__(self, name, src, dst, instructions=0, bytes=0, broadcasting=False):
        super(RandomMessage, self).__init__(
            name, src, dst, instructions, bytes, broadcasting
        )
        self.inst_range = (
            instructions
            if isinstance(instructions, (list, tuple))
            else (instructions, instructions)
        )
        self.bytes_range = bytes if isinstance(bytes, (list, tuple)) else (bytes, bytes)

    def __copy__(self):
        new_msg = RandomMessage(
            self.name,
            self.src,
            self.dst,
            self.inst_range,
            self.bytes_range,
            self.broadcasting,
        )
        new_msg.inst = random.randint(self.inst_range[0], self.inst_range[1])
        new_msg.bytes = random.randint(self.bytes_range[0], self.bytes_range[1])

        # Copy internal attributes from the parent Message class
        new_msg.timestamp = self.timestamp
        new_msg.id = self.id
        new_msg.original_DES_src = self.original_DES_src

        return new_msg
