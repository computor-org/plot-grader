"""Execute Python plotting code safely and extract matplotlib figures."""

import io
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, Any
import traceback


def execute_plot_code(code_path: Path) -> Dict[str, Any]:
    """
    Execute Python plotting code and capture matplotlib figure.

    Args:
        code_path: Path to Python file to execute

    Returns:
        Dict with:
            - success: bool
            - figure: matplotlib Figure object (if successful)
            - error: str (if failed)
            - namespace: dict of variables (if successful)
    """
    # Clear any existing figures
    plt.close('all')

    # Create isolated namespace
    namespace = {
        '__file__': str(code_path.absolute()),
        '__name__': '__main__',
    }

    try:
        # Read and execute code
        code = code_path.read_text()

        # Replace plt.show() with pass to prevent blocking
        code = code.replace('plt.show()', 'pass')

        exec(code, namespace)

        # Get the current figure
        figs = [plt.figure(n) for n in plt.get_fignums()]

        if not figs:
            return {
                'success': False,
                'error': 'No matplotlib figure created',
                'figure': None,
                'namespace': namespace,
            }

        # Use the first figure (most assignments create only one)
        figure = figs[0]

        return {
            'success': True,
            'figure': figure,
            'error': None,
            'namespace': namespace,
        }

    except Exception as e:
        return {
            'success': False,
            'error': f"{type(e).__name__}: {str(e)}",
            'traceback': traceback.format_exc(),
            'figure': None,
            'namespace': namespace,
        }


def extract_plot_data(figure: matplotlib.figure.Figure) -> Dict[str, Any]:
    """
    Extract structured data from matplotlib figure for analysis.

    Args:
        figure: Matplotlib Figure object

    Returns:
        Dict with plot metadata and line/axis information
    """
    if not figure or not figure.axes:
        return {'axes': []}

    data = {'axes': []}

    for ax_idx, ax in enumerate(figure.axes):
        ax_data = {
            'index': ax_idx,
            'xlabel': ax.get_xlabel(),
            'ylabel': ax.get_ylabel(),
            'title': ax.get_title(),
            'xlim': ax.get_xlim(),
            'ylim': ax.get_ylim(),
            'lines': [],
        }

        # Extract line data
        for line_idx, line in enumerate(ax.lines):
            line_data = {
                'index': line_idx,
                'xdata': line.get_xdata(),
                'ydata': line.get_ydata(),
                'color': line.get_color(),
                'linestyle': line.get_linestyle(),
                'linewidth': line.get_linewidth(),
                'marker': line.get_marker(),
                'label': line.get_label(),
            }
            ax_data['lines'].append(line_data)

        data['axes'].append(ax_data)

    return data


def render_figure_to_bytes(figure: matplotlib.figure.Figure,
                           dpi: int = 100,
                           figsize: tuple = (8, 6)) -> bytes:
    """
    Render matplotlib figure to PNG bytes.

    Args:
        figure: Matplotlib Figure object
        dpi: Resolution in dots per inch
        figsize: Figure size in inches (width, height)

    Returns:
        PNG image as bytes
    """
    figure.set_size_inches(figsize)
    buf = io.BytesIO()
    figure.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    return buf.read()
