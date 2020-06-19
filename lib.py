from __future__ import print_function
import sys, math, re

min_penup_travel_distance = 1 # in mm, shorter travels will be removed
pendown_value = 'G0 F500.000 Z160.000'
penup_value = 'G0 F500.000 Z90.000'
feedrate_value = 'F60.000'

def calculate_distance(coordinates1, coordinates2):
    x1 = coordinates1[0]
    y1 = coordinates1[1]
    x2 = coordinates2[0]
    y2 = coordinates2[1]
    dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)  
    return dist

def replace_text_between(original_text, delimeter_a, delimeter_b, replacement_text):
    # parts = original_text.split(delimeter_a)
    # leadingText = parts.pop(0) # keep everything beofe first delimterA
    # parts = delimeter_a.join(parts).split(delimeter_b)
    # parts.pop(0) # remove everything before first delimeter_b
    # trailingText = delimeter_b.join(parts) # keep everything after first delimeter_b 
    
    # return leadingText + delimeter_a + replacement_text + delimeter_b + trailingText

    reg = "(?<=%s).*?(?=%s)" % (delimeter_a, delimeter_b)
    r = re.compile(reg,re.DOTALL)
    result = r.sub(replacement_text, original_text)

    return result

class Instruction():

    def __init__(self, line):
        self.line = line.rstrip()
        self.typecode = self.line.split(' ')[0]
        self.typename = self._typename()

        self.coords = self._coords()

    def distance_to(self, other):
        # return max(abs(other.coords[0] - self.coords[0]), abs(other.coords[1] - self.coords[1]))
        return calculate_distance(self.coords, other.coords)

    def _typename(self):

        if pendown_value in self.line:
            return 'pendown'
        elif penup_value in self.line:
            return 'penup'
        elif self.typecode == "G0" or self.typecode == "G1":                    
            return 'move'
        else:
            return 'other'

    def _coords(self):
        try:
            # Try to extract coordinates.
            x = self.line.split('X')[1].split(" ")[0]
            y = self.line.split('Y')[1].split(" ")[0]
            return (float(x), float(y))
        except IndexError:
            return None

class Glyph():
    def __init__(self, instructions):
        self._reversed = False
        try:
            self.start = instructions[0].coords
            self.end = instructions[-2].coords
        except IndexError:
            self.start = None
            self.end = None

        if self.start == None or self.end == None:
            print("Problem with instructions in glyph:", file=sys.stderr)
            for i in instructions:
                print("%s (%s)" % (i.line, i.typename), file=sys.stderr)

        self.instructions = instructions

    def distance_to(self, other):
        """
        Compute distance between two glyphs
        """
        # return max(abs(other.start[0] - self.end[0]), abs(other.start[1] - self.end[1]))
        return calculate_distance(self.end, other.start)

    def distance_to_if_other_reversed(self, other):
        # return max(abs(other.end[0] - self.end[0]), abs(other.end[1] - self.end[1]))
        return calculate_distance(self.end, other.end)

    def _reversed_instructions(self):
        """
        A generator of the reversed instructions.

        Typical instructions look like this (normal ordering):

        G1 F100.000 X250.066 Y-439.295  <-- startpoint (assumed pen is up)
        G0 F500.000 Z160.000            <-- pendown
        G0 F60.000 X250.409 Y-439.954   <-- drawing moves ...
        G0 X248.001 Y-441.921
        G0 X245.314 Y-443.391           <-- last move
        G0 F500.000 Z90.000             <-- penup

        So a reversed ordering would print in this order:

        startpoint, G1, but with coordinates from last move 
        pendown
        other moves in reversed order
        last move, G0, but with coordinates from startpoint
        penup

        """
        original_order = iter(self.instructions)
        reverse_order = reversed(self.instructions)

        startpoint = next(original_order)
        pendown = next(original_order)

        penup = next(reverse_order)
        endpoint = next(reverse_order)
        
        endpoint.line = replace_text_between(startpoint.line, "X", " ", str(endpoint.coords[0]))
        endpoint.line = replace_text_between(startpoint.line, "Y", " ", str(endpoint.coords[1]))
        startpoint.line = replace_text_between(endpoint.line, "X", " ", str(startpoint.coords[0]))
        startpoint.line = replace_text_between(endpoint.line, "Y", " ", str(startpoint.coords[1]))

        endpoint.typecode = endpoint.line.split(' ')[0]
        startpoint.typecode = startpoint.line.split(' ')[0]

        yield endpoint
        yield pendown

        for i in reverse_order:
            if not i.typename == 'move':
                break
            yield i

        yield startpoint
        yield penup

    def ordered_instructions(self):
        if self._reversed:
            return self._reversed_instructions()
        else:
            return iter(self.instructions)

    def reversed_copy(self):
        if not hasattr(self, '_reversed_copy'):
            from copy import copy
            new = copy(self)
            new.start = self.end
            new.end = self.start
            new._reversed = True
            new._reversed_copy = self
            self._reversed_copy = new
        return self._reversed_copy

    def __hash__(self):
        return hash("\n".join([i.line for i in self.instructions]))

def total_penup_travel(gs):
    """
    Compute total distance traveled in a given ordering
    """
    def distance_between_each_pair(gs):
        gs = iter(gs)
        prev = next(gs)
        for g in gs:
            yield prev.distance_to(g)
            prev = g

    return sum(distance_between_each_pair(gs))

def total_travel(gs):
    def iter_moves(gs):
        for g in gs:
            for i in g.ordered_instructions():
                if i.typename == 'move':
                    yield i

    def distance_between_moves(moves):
        moves = iter(moves)
        prev = next(moves)
        for m in moves:
            yield prev.distance_to(m)
            prev = m

    return sum(distance_between_moves(iter_moves(gs)))

def reorder_greedy(gs, index=0):
    """
    Greedy sorting: pick a starting glyph, then find the glyph which starts
    nearest to the previous ending point.

    This is O(n^2). Pretty sure it can't be optimized into a sort.
    """
    from operator import itemgetter
    gs = list(gs)
    ordered = [gs.pop(index)]
    prev = ordered[0]

    def dist_reverse_iterator(gs):
        for g in gs:
            yield (prev.distance_to(g), False, g)
            yield (prev.distance_to_if_other_reversed(g), True, g)

    while len(gs) > 0:
        (dist, reverse, nearest) = min(dist_reverse_iterator(gs),
                                       key=itemgetter(0, 1))
        gs.remove(nearest)

        if reverse:
            prev = nearest.reversed_copy()
        else:
            prev = nearest

        ordered.append(prev)

    return ordered

def prune_small_distance_penups(instructions):
    instructions = iter(instructions)
    try:
        prev = next(instructions)
    except StopIteration:
        raise ValueError("instructions empty")
    # The first instruction should always be a penup, so we send it straight
    # through.
    yield prev

    try:
        while True:
            current = next(instructions)
            if current.typename == 'penup':
                last_down = prev
                penup = current

                # Get all moves while the pen is up. There should only ever be
                # one, but you never know these days. :-)
                moves = []
                try:
                    while True:
                        penup_move = next(instructions)
                        if penup_move.typename == 'pendown':
                            pendown = penup_move
                            break
                        else:
                            moves.append(penup_move)
                except StopIteration:
                    # If we reach the end of the instructions while looking for
                    # a pendown, raise the pen and call it good.
                    yield penup
                    raise StopIteration

                if calculate_distance(moves[-1].coords, last_down.coords) <= min_penup_travel_distance:
                    # The penup move(s) didn't travel the minimum desired distance,
                    # so we remove them from the list of instructions and continue
                    # to the next instruction.
                    continue
                else:
                    # The penup move(s) DID move enough, so we keep them.
                    yield penup
                    for move in moves:
                        yield move
                    yield pendown
            else:
                yield current
            prev = current

    except StopIteration:
        pass

def clean_instructions(instructions):
    cleaned = []
    is_pen_up = True
    clean_instructions.prev = None

    def keep_instruction(instruction):
        if (instruction.typecode == "G0" and instruction.coords is not None):
            if ((clean_instructions.prev.typename == 'pendown') and clean_instructions.prev is not None) and ("F" not in instruction.line):
                # Insert feed rate for first pendown move
                instruction.line = replace_text_between(instruction.line, "G0 ", "X", feedrate_value + " ")
            elif ("F" in instruction.line):
                # Remove feed rate for next moves
                instruction.line = replace_text_between(instruction.line, "G0 ", "X", "")
            
        clean_instructions.prev = instruction
        cleaned.append(instruction)

    for instruction in instructions:
        if instruction.typename == 'penup':
            is_pen_up = True
        elif instruction.typename == 'pendown':
            is_pen_up = False

        if (instruction.typecode == "G1"):
            if is_pen_up:
                # Keep G1 instruction if pen is up
                keep_instruction(instruction)
            else:
                # If pen is down, it should be a G0 move.
                # Only keep if it travels a distance
                if(clean_instructions.prev is not None and clean_instructions.prev.coords):

                    if calculate_distance(clean_instructions.prev.coords, instruction.coords) > 0:
                        instruction.typecode = "G0"
                        instruction.line = instruction.line.replace("G1", "G0")
                        keep_instruction(instruction)
        else:

            if instruction.typecode == "G0" and instruction.coords is not None and clean_instructions.prev is not None and clean_instructions.prev.coords is not None:
                if not (calculate_distance(clean_instructions.prev.coords, instruction.coords) > 0):
                    # Skip duplicate instruction
                    continue
            
            # Keep these instructions
            keep_instruction(instruction)

    return cleaned

def dedupe(gs):
    "Use Glyph.__hash__() to dedupe the list of glyphs"
    seen = set()
    for g in gs:
        h = hash(g)
        if h not in seen:
            yield g
            seen.add(h)

def iter_instructions(gs):
    # be sure to start with a penup
    yield Instruction(penup_value)
    for g in gs:
        for i in g.ordered_instructions():
            yield i
