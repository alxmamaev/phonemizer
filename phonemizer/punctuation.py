# Copyright 2015-2021 Mathieu Bernard
#
# This file is part of phonemizer: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Phonemizer is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with phonemizer. If not, see <http://www.gnu.org/licenses/>.
"""Implementation of punctuation processing"""

import collections
import re
from typing import List, Union, Tuple
from tqdm import tqdm

from phonemizer.utils import str2list

# The punctuation marks considered by default.
_DEFAULT_MARKS = ';:,.!?¡¿—…"«»“”'

_MarkIndex = collections.namedtuple(
    '_mark_index', ['index', 'mark', 'position'])


class Punctuation:
    """Preserve or remove the punctuation during phonemization

    Backends behave differently with punctuation: festival and espeak ignore it
    and remove it silently whereas segments will raise an error. The
    Punctuation class solves that issue by "hiding" the punctuation to the
    phonemization backend and restoring it afterwards.

    Parameters
    ----------
    marks (str) : The list of punctuation marks to considerate for processing
        (either removal or preservation). Each mark must be made of a single
        character. Default to Punctuation.default_marks().

    """

    def __init__(self, marks: str = _DEFAULT_MARKS):
        self._marks: str = None  # noqa
        self._marks_re: re.Pattern[str] = None  # noqa
        self.marks = marks

    @staticmethod
    def default_marks():
        """Returns the default punctuation marks as a string"""
        return _DEFAULT_MARKS

    @property
    def marks(self):
        """The punctuation marks as a string"""
        return self._marks

    @marks.setter
    def marks(self, value: str):
        if not isinstance(value, str):
            raise ValueError('punctuation marks must be defined as a string')
        self._marks = ''.join(set(value))

        # catching all the marks in one regular expression: zero or more spaces
        # + one or more marks + zero or more spaces.
        self._marks_re = re.compile(fr'(\s*[{re.escape(self._marks)}]+\s*)+')

    def remove(self, text: Union[str, List[str]]) -> Union[str, List[str]]:
        """Returns the `text` with all punctuation marks replaced by spaces

        The input `text` can be a string or a list and is returned with the
        same type and punctuation removed.

        """

        def aux(text: str) -> str:
            return re.sub(self._marks_re, ' ', text).strip()

        if isinstance(text, str):
            return aux(text)
        return [aux(line) for line in text]

    def preserve(self, text: Union[List[str], str]) -> Tuple[List[List[str]], List[_MarkIndex]]:
        """Removes punctuation from `text`, allowing for furter restoration

        This method returns the text as a list of punctuated chunks, along with
        a list of punctuation marks for furter restoration:

            'hello, my world!' -> ['hello', 'my world'], [',', '!']

        """
        text: List[str] = str2list(text)
        preserved_text = []
        preserved_marks = []

        for num, line in enumerate(text):
            line, marks = self._preserve_line(line, num)
            preserved_text += line
            preserved_marks += marks
        return [line for line in preserved_text if line], preserved_marks

    def _preserve_line(self, line: str, num: int) -> Tuple[List[str], List[_MarkIndex]]:
        """Auxiliary method for Punctuation.preserve()"""
        matches = list(re.finditer(self._marks_re, line))
        if not matches:
            return [line], []

        # the line is made only of punctuation marks
        if len(matches) == 1 and matches[0].group() == line:
            return [], [_MarkIndex(num, line, 'A')]

        # build the list of mark indexes required to restore the punctuation
        marks = []
        for match in matches:
            # find the position of the punctuation mark in the utterance:
            # begin (B), end (E), in the middle (I) or alone (A)
            position = 'I'
            if match == matches[0] and line.startswith(match.group()):
                position = 'B'
            elif match == matches[-1] and line.endswith(match.group()):
                position = 'E'
            marks.append(_MarkIndex(num, match.group(), position))

        # split the line into sublines, each separated by a punctuation mark
        preserved_line = []
        for mark in marks:
            split = line.split(mark.mark)
            prefix, suffix = split[0], mark.mark.join(split[1:])
            preserved_line.append(prefix)
            line = suffix

        # append any trailing text to the preserved line
        return preserved_line + [line], marks

    @classmethod
    def restore(cls, text: Union[str, List[str]], marks: List[_MarkIndex]):
        text = str2list(text)
        punctuated_text = []
        pos = 0
        with tqdm() as pbar:
            while text or marks:
                if not marks:
                    merged_text = ''.join(text)
                    punctuated_text.append(merged_text)
                    text = []
                elif not text:
                    # nothing has been phonemized, returns the marks alone, with internal
                    # spaces replaced by the word separator
                    merged_marks = [''.join(m.mark for m in marks)]
                    # if strip is False, ensure the final mark ends with a word separator
                    punctuated_text.append(merged_marks)
                    marks = []

                else:
                    current_mark = marks[0]
                    if current_mark.index == pos:

                        # place the current mark here
                        mark = marks[0]
                        marks = marks[1:]
                        # replace internal spaces in the current mark with the word separator
                        text[0] = text[0].rstrip()
                        # remove the word last separator from the current word
                        if current_mark.position == 'B':
                            text[0] = mark.mark + text[0]
                        elif current_mark.position == 'E':
                            punctuated_text.append(text[0] + mark.mark + '')
                            text = text[1:]
                            pos = pos + 1
                        elif current_mark.position == 'A':
                            punctuated_text.append(mark.mark + '')
                            pos = pos + 1
                        else:
                            # position == 'I'
                            if len(text) == 1:  # pragma: nocover
                                # a corner case where the final part of an intermediate
                                # mark (I) has not been phonemized
                                text[0] = text[0] + mark.mark
                            else:
                                first_word = text[0]
                                text = text[1:]
                                text[0] = first_word + mark.mark + text[0]

                    else:
                        punctuated_text.append(text[0])
                        text = text[1:]
                        pos = pos + 1
            pbar.update()


        return punctuated_text