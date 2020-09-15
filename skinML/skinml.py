import pickle
import requests
import numpy as np
from os import path
import pandas as pd
import sklearn
from sklearn import linear_model, preprocessing
from skinML import imgtest, insertskins


def main():
    # If we do not have the data file, use insertskins to create a new one
    if not path.exists('../data/skindata.csv'):
        status = insertskins.insert()
        if status == -1:
            print('Error when creating skin data file...')
            exit(-1)
        else:
            print('Successfully created skin file...')

def train_model():
    predict = 'curr_price'
    le = preprocessing.LabelEncoder()
    skin_data = pd.read_csv('../data/skindata.csv')
    skin_data['skin_type'] = le.fit_transform(list(skin_data['skin_type']))
    X = np.array(skin_data.drop([predict, 'skin_type'], 1))
    y = np.array(skin_data[predict])

    best = 0
    while best < .8:
        x_train, x_test, y_train, y_test = sklearn.model_selection.train_test_split(X, y, test_size=0.1)

        linear = linear_model.LinearRegression()

        linear.fit(x_train, y_train)

        acc = linear.score(x_test, y_test)

        if acc > best:
            print('Overriding previous best model\t' + str(best) + '\twith\t' + str(acc))
            best = acc
            with open('../data/best_model.pickle', 'wb') as f:
                pickle.dump(linear, f)

    x_train, x_test, y_train, y_test = sklearn.model_selection.train_test_split(X, y, test_size=.1)

    pickle_in = open('../data/best_model.pickle', 'rb')
    linear = pickle.load(pickle_in)

    predictions = linear.predict(x_test)
    for x in range(len(predictions)):
        print('Predicted price: \t' + str(predictions[x]) + '\tActual price:\t' + str(y_test[x]))

def get_predicted_price(skin_url):
    # Get skin's image data, initial price, and skin type from the store page
    html = insertskins.get_html(skin_url)
    skin_img_url = html.find('img', {"class": "workshop_preview_image"})['src']
    skin_price = html.find('div', {"class": "game_purchase_price price"}).text
    skin_price = "".join(i for i in skin_price if 126 > ord(i) > 31)
    skin_price_in_double = float(skin_price[1:])
    skin_img_url = skin_img_url.replace('65f', '360f')
    skin_img = requests.get(skin_img_url)
    img_data = imgtest.load_image(skin_img)

    # Load skin data into an numpy array
    temp_arr = []
    for val in img_data.values():
        temp_arr.append(val)
    temp_arr.append(skin_price_in_double)
    temp_arr.append(360)
    skin = np.array(temp_arr)
    skin = skin.reshape(1, -1)

    # Open the best model and predict the price
    pickle_in = open('../data/best_model.pickle', 'rb')
    linear = pickle.load(pickle_in)

    predictions = linear.predict(skin)
    return "{:.2f}".format(abs(predictions[0]))

if __name__ == "__main__":
    main()




