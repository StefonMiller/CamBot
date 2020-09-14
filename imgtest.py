import numpy as np
from matplotlib import colors
from scipy.spatial import cKDTree as KDTree
from PIL import Image
from io import BytesIO
import pandas as pd
import matplotlib.pyplot as plt

counts = ''


# Prevent anything from running when imported
def main():
    pass


if __name__ == "__main__":
    main()



# Shows image plots for all data corresponding to price to visualize relationships.
def show_relationships():
    skin_data = pd.read_csv('skindata.csv')
    for column in skin_data.drop('curr_price', 1):
        plt.xlabel(column)
        plt.ylabel('Current Price')
        plt.scatter(skin_data[column], skin_data['curr_price'])
        plt.show()


def get_colors():
    return ['red', 'orange', 'yellow', 'green', 'blue', 'white', 'brown', 'cyan', 'gray', 'pink', 'darkslategray']


def load_image(resp):
    all_colors = False

    # borrow a list of named colors from matplotlib
    if not all_colors:
        use_colors = {k: colors.cnames[k] for k in ['red', 'orange', 'yellow', 'green', 'blue', 'purple', 'white',
                                                    'black', 'brown', 'cyan', 'gray', 'pink', 'darkslategray']}
    else:
        use_colors = colors.cnames

    # translate hexstring to RGB tuple
    named_colors = {k: tuple(map(int, (v[1:3], v[3:5], v[5:7]), 3 * (16,)))
                    for k, v in use_colors.items()}
    ncol = len(named_colors)

    if not all_colors:
        ncol -= 1
        no_match = named_colors.pop('purple')
    else:
        no_match = named_colors['purple']

    # make an array containing the RGB values
    color_tuples = list(named_colors.values())
    color_tuples.append(no_match)
    color_tuples = np.array(color_tuples)

    color_names = list(named_colors)
    color_names.append('no match')

    img = Image.open(BytesIO(resp.content))
    img = img.convert('RGB')
    img = np.array(img)

    # build tree
    tree = KDTree(color_tuples[:-1])
    # tolerance for color match `inf` means use best match no matter how
    # bad it may be
    tolerance = np.inf
    # find closest color in tree for each pixel in picture
    dist, idx = tree.query(img, distance_upper_bound=tolerance)
    # count and reattach names
    counts = dict(zip(color_names, np.bincount(idx.ravel(), None, ncol + 1)))

    counts.pop('black')
    return counts
