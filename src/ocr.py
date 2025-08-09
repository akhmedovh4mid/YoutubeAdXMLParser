import math
from dataclasses import dataclass
from typing import List, Literal, Optional

import pytesseract
from PIL.Image import Image as PILImage
from PIL.ImageEnhance import Contrast


@dataclass
class TesseractResult:
    level: List[int]
    page_num: List[int]
    block_num: List[int]
    par_num: List[int]
    line_num: List[int]
    word_num: List[int]
    left: List[int]
    top: List[int]
    width: List[int]
    height: List[int]
    conf: List[int]
    text: List[str]


@dataclass
class TesseractCoords:
    top: int
    left: int
    width: int
    height: int


class Tesseract:
    @staticmethod
    def get_screen_data(
        image: PILImage,
        lang: str = "eng",
        contrast_factor: float = 1.5,
        scale: Optional[Literal[2, 4, 8]] = None,
    ) -> TesseractResult:
        if scale:
            image = image.resize(size=(image.width * scale, image.height * scale))

        if lang != "eng":
            lang = f"{lang}+eng"

        if contrast_factor != 1.0:
            image = Contrast(image).enhance(contrast_factor)

        data_dict: dict = pytesseract.image_to_data(
            image=image, lang=lang, output_type=pytesseract.Output.DICT
        )
        data = TesseractResult(**data_dict)

        if scale:
            data.top = [math.floor(i / scale) for i in data.top]
            data.left = [math.floor(i / scale) for i in data.left]
            data.width = [math.ceil(i / scale) for i in data.width]
            data.height = [math.ceil(i / scale) for i in data.height]

        return data

    @staticmethod
    def find_matches_by_word(
        lang: str,
        image: PILImage,
        target_word: str,
        contrast_factor: float = 1.5,
        scale: Optional[Literal[2, 4, 8]] = None,
    ) -> Optional[TesseractCoords]:
        image_data: TesseractResult = Tesseract.get_screen_data(
            image=image,
            scale=scale,
            lang=lang,
            contrast_factor=contrast_factor,
        )

        words = [w.lower() for w in image_data.text]
        target_words = target_word.lower().split()

        for i in range(len(words) - len(target_words) + 1):
            if words[i : i + len(target_words)] == target_words:
                top = min(image_data.top[i : i + len(target_words)])
                left = min(image_data.left[i : i + len(target_words)])
                width = (
                    max(
                        [
                            image_data.left[j] + image_data.width[j]
                            for j in range(i, i + len(target_words))
                        ]
                    )
                    - left
                )
                height = (
                    max(
                        [
                            image_data.top[j] + image_data.height[j]
                            for j in range(i, i + len(target_words))
                        ]
                    )
                    - top
                )
                return TesseractCoords(top=top, left=left, width=width, height=height)

        return None
