import sys
import os
import pygame


def variant_a(surface: pygame.Surface) -> pygame.Surface:
    """Вариант А: colorkey чистого белого. Риск: белые пиксели ВНУТРИ спрайта станут прозрачными."""
    out = surface.copy()
    out.set_colorkey((255, 255, 255))
    return out


def variant_b(surface: pygame.Surface, threshold: int = 220) -> pygame.Surface:
    """Вариант Б (аппроксимация get_rect): порог 220 → чёрный + colorkey чёрного.
    Риск: светлые пиксели тайлов ПОЛА (стены/свет) сотрутся."""
    arr = pygame.surfarray.array3d(surface.copy())
    mask = (
        (arr[:, :, 0] >= threshold)
        & (arr[:, :, 1] >= threshold)
        & (arr[:, :, 2] >= threshold)
    )
    arr[mask] = (0, 0, 0)
    out = pygame.surfarray.make_surface(arr)
    out.set_colorkey((0, 0, 0))
    return out


def main(paths: list[str]) -> None:
    pygame.init()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    for p in paths:
        sheet = pygame.image.load(p)
        base = os.path.splitext(os.path.basename(p))[0]
        a = variant_a(sheet)
        b = variant_b(sheet)
        pygame.image.save(a, os.path.join(out_dir, f"probe_{base}_A_colorkey.png"))
        pygame.image.save(b, os.path.join(out_dir, f"probe_{base}_B_threshold.png"))
        # Количественная метрика: сколько пикселей Вариант Б убил, а А оставил
        arr_orig = pygame.surfarray.array3d(sheet)
        arr_a = pygame.surfarray.array3d(a)
        killed_b = int(
            (
                (arr_orig[:, :, 0] >= 220)
                & (arr_orig[:, :, 1] >= 220)
                & (arr_orig[:, :, 2] >= 220)
            ).sum()
        )
        # Метрика риска Варианта Б: сколько светлых пикселей (жертвы порога 220)
        # содержит оригинал листа. Чем больше — тем опаснее вариант Б для
        # светлых тайлов (пол/свет). Прозрачность А не измеряем попиксельно:
        # colorkey честно виден на сохранённом PNG.
        killed_by_b = int(
            (
                (arr_orig[:, :, 0] >= 220)
                & (arr_orig[:, :, 1] >= 220)
                & (arr_orig[:, :, 2] >= 220)
            ).sum()
        )
        print(f"[BUG07_PROBE] {base}: pixels_at_risk_from_threshold220={killed_by_b}, size={sheet.get_size()}, A/B PNG сохранены")


if __name__ == "__main__":
    main(sys.argv[1:])