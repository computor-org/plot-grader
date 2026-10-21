"""Generate stress test variants for assignments."""

from pathlib import Path
from typing import List
import textwrap


class PlotDocstrStressTests:
    """Generate stress test variants for plot_docstr assignment."""

    @staticmethod
    def generate_positive_variants(output_dir: Path) -> List[Path]:
        """
        Generate positive variants (should pass).

        Returns list of paths to generated Python files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        variants = []

        # Variant 1: Reverse order
        variant_path = output_dir / "positive_01_reverse_order.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            # Reverse plot order
            plt.plot(x, y_3, "k:")
            plt.plot(x, y_2, "b--")
            plt.plot(x, y_1, "r-")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 2: Different order
        variant_path = output_dir / "positive_02_mixed_order.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            # Mixed plot order
            plt.plot(x, y_2, "b--")
            plt.plot(x, y_3, "k:")
            plt.plot(x, y_1, "r-")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 3: Explicit color names
        variant_path = output_dir / "positive_03_color_names.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            plt.plot(x, y_1, color="red", linestyle="-")
            plt.plot(x, y_2, color="blue", linestyle="--")
            plt.plot(x, y_3, color="black", linestyle=":")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 4: Hex colors
        variant_path = output_dir / "positive_04_hex_colors.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            plt.plot(x, y_1, color="#FF0000", linestyle="-")
            plt.plot(x, y_2, color="#0000FF", linestyle="--")
            plt.plot(x, y_3, color="#000000", linestyle=":")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 5: OOP interface
        variant_path = output_dir / "positive_05_oop_interface.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            fig, ax = plt.subplots()
            ax.plot(x, y_1, "r-")
            ax.plot(x, y_2, "b--")
            ax.plot(x, y_3, "k:")

            ax.set_xlim(min(x), max(x))
            ax.set_ylim(min(y_3), max(y_3))
            ax.set_xlabel("x")
            ax.set_ylabel("f(x)")
            ax.set_title("Test")
        ''').strip())
        variants.append(variant_path)

        return variants

    @staticmethod
    def generate_negative_variants(output_dir: Path) -> List[Path]:
        """
        Generate negative variants (should fail).

        Returns list of paths to generated Python files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        variants = []

        # Variant 1: Missing curve
        variant_path = output_dir / "negative_01_missing_curve.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            # Only 2 curves instead of 3
            plt.plot(x, y_1, "r-")
            plt.plot(x, y_2, "b--")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 2: Wrong color
        variant_path = output_dir / "negative_02_wrong_color.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            # Wrong color on first line (blue instead of red)
            plt.plot(x, y_1, "b-")
            plt.plot(x, y_2, "r--")
            plt.plot(x, y_3, "k:")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 3: Wrong linestyle
        variant_path = output_dir / "negative_03_wrong_linestyle.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            # Wrong linestyle (dashed instead of solid)
            plt.plot(x, y_1, "r--")
            plt.plot(x, y_2, "b-")
            plt.plot(x, y_3, "k:")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 4: Wrong data (small error)
        variant_path = output_dir / "negative_04_wrong_data_small.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x * 1.1  # 10% error
            y_2 = x**2
            y_3 = x**3

            plt.plot(x, y_1, "r-")
            plt.plot(x, y_2, "b--")
            plt.plot(x, y_3, "k:")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 5: Missing label
        variant_path = output_dir / "negative_05_missing_label.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # Use same x-range as reference but avoid exact signature
            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            plt.plot(x, y_1, "r-")
            plt.plot(x, y_2, "b--")
            plt.plot(x, y_3, "k:")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            # Missing xlabel
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        return variants

    @staticmethod
    def generate_ambiguous_variants(output_dir: Path) -> List[Path]:
        """
        Generate ambiguous variants (for testing Tier 2/3).

        These should require fallthrough from Tier 1 to later tiers.

        Returns list of paths to generated Python files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        variants = []

        # Variant 1: Borderline data error (3% off - might be acceptable)
        variant_path = output_dir / "ambiguous_01_small_data_error.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x * 1.03  # 3% error - borderline
            y_2 = x**2
            y_3 = x**3

            plt.plot(x, y_1, "r-")
            plt.plot(x, y_2, "b--")
            plt.plot(x, y_3, "k:")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 2: Very similar but not exact color (dark red vs red)
        variant_path = output_dir / "ambiguous_02_similar_color.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            # Dark red instead of pure red (0.8, 0, 0) vs (1.0, 0, 0)
            plt.plot(x, y_1, color=(0.8, 0, 0), linestyle="-")
            plt.plot(x, y_2, "b--")
            plt.plot(x, y_3, "k:")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 3: Slightly different axis limits (5% larger)
        variant_path = output_dir / "ambiguous_03_axis_limits.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            plt.plot(x, y_1, "r-")
            plt.plot(x, y_2, "b--")
            plt.plot(x, y_3, "k:")

            # 5% larger limits
            plt.xlim(min(x) * 1.05, max(x) * 1.05)
            plt.ylim(min(y_3) * 1.05, max(y_3) * 1.05)
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 4: Different but visually similar linestyle
        variant_path = output_dir / "ambiguous_04_linestyle_variant.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            x = np.linspace(-3.14159, 3.14159, 200)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            plt.plot(x, y_1, "r-")
            # Dash-dot instead of dashed (similar but different)
            plt.plot(x, y_2, "b-.")
            plt.plot(x, y_3, "k:")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        # Variant 5: Fewer data points but visually similar
        variant_path = output_dir / "ambiguous_05_fewer_points.py"
        variant_path.write_text(textwrap.dedent('''
            import numpy as np
            import matplotlib.pyplot as plt

            # 50 points instead of 200 - visually similar but different
            x = np.linspace(-3.14159, 3.14159, 50)
            y_1 = x
            y_2 = x**2
            y_3 = x**3

            plt.plot(x, y_1, "r-")
            plt.plot(x, y_2, "b--")
            plt.plot(x, y_3, "k:")

            plt.xlim(min(x), max(x))
            plt.ylim(min(y_3), max(y_3))
            plt.xlabel("x")
            plt.ylabel("f(x)")
            plt.title("Test")
        ''').strip())
        variants.append(variant_path)

        return variants
