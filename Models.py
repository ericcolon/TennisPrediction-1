import collections
import pickle
import statistics as s
from collections import defaultdict
from random import random

import matplotlib.pyplot as plt
import numpy as np
from sklearn import preprocessing
from sklearn import svm
from sklearn import tree
from sklearn.externals import joblib
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import train_test_split
from sqlalchemy import create_engine

from DataExtraction import *


# Methods to convert pandas dataframe into sqlite3 database
def df2sqlite(dataframe, db_name="import.sqlite", tbl_name="import"):
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()

    wildcards = ','.join(['?'] * len(dataframe.columns))
    data = [tuple(x) for x in dataframe.values]

    cur.execute("drop table if exists %s" % tbl_name)

    col_str = '"' + '","'.join(dataframe.columns) + '"'
    cur.execute("create table %s (%s)" % (tbl_name, col_str))

    cur.executemany("insert into %s values(%s)" % (tbl_name, wildcards), data)

    conn.commit()
    conn.close()


def df2sqlite_v2(dataframe, db_name):
    disk_engine = create_engine('sqlite:///' + db_name + '.db')
    dataframe.to_sql(db_name, disk_engine, if_exists='append')


def show_deadline(conn, column_list):
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    sql = "SELECT * FROM stats"
    cursor.execute(sql)
    row = cursor.fetchone()
    for col in column_list:
        print('  column:', col)
        print('    value :', row[col])
        print('    type  :', type(row[col]))
    return


def test_model(modelname, dataset_name, labelset_name, split):
    pickle_in = open(dataset_name, "rb")
    x = np.asarray(pickle.load(pickle_in))
    pickle_in_2 = open(labelset_name, "rb")
    y = np.asarray(pickle.load(pickle_in_2))
    model = joblib.load(modelname)
    rev_X = x[::-1]
    rev_y = y[::-1]
    number_of_columns = rev_X.shape[1] - 1
    print(number_of_columns)

    # Before standardizing we want to take out the H2H column

    h2h = rev_X[:, number_of_columns]
    print(rev_X.shape)
    print(h2h.shape)

    # Delete this specific column
    rev_X = np.delete(rev_X, np.s_[-1], 1)
    print(rev_X.shape)
    print((rev_X.shape[1]))
    # Before
    # This line standardizes a feature X by dividing it by its standard deviation.
    X_scaled = preprocessing.scale(rev_X, with_mean=False)
    X_scaled = np.column_stack((X_scaled, h2h))
    print(X_scaled.shape)

    X_train, X_test, y_train, y_test = train_test_split(X_scaled, rev_y, test_size=split, shuffle=False)

    print("Training accuracy for {} on {} and {} is: {}".format(modelname, dataset_name, labelset_name,
                                                                model.score(X_train, y_train)))

    print("Testing accuracy for {} on {} and {} is: {}".format(modelname, dataset_name, labelset_name,
                                                               model.score(X_test, y_test)))


def tune_sgd_hyperparameters(x_train, y_train, x_dev, y_dev):
    # [0.00001, 0.0001, 0.001, 0.1, 1, 10] these are the values for alpha
    parameter_values = ['hinge', 'log', 'modified_huber', 'squared_hinge', 'perceptron', 'squared_loss']
    xi = [i for i in range(0, len(parameter_values))]

    parameter_scores = []

    for param in parameter_values:
        # We plot different alpha values with their dev accuracies
        model = SGDClassifier(loss=param, alpha=0.1)
        model.fit(x_train, y_train)

        acc = model.score(x_dev, y_dev)
        print(acc)
        parameter_scores.append(acc)

    plt.plot(xi, parameter_scores, marker='o',
             linestyle='--', color='r', label='alpha')

    plt.xlabel('Loss function for SGD')
    plt.ylabel('Accuracy of Dev Data in Percentage')
    plt.xticks(xi, parameter_values)
    plt.legend()
    plt.show()


# Used in prediction mode of Decision Stump Model
def preprocess_features_of_predictions(features, standard_deviations):
    features = features[~np.all(features == 0, axis=1)]
    h2h_pred = features[:, features.shape[1] - 1]
    features_shortened = np.delete(features, np.s_[-1], 1)
    features_scaled = features_shortened / standard_deviations[None, :]
    features_final = np.column_stack(
        (features_scaled, h2h_pred))  # Add H2H statistics back to the mix
    return features_final


# Helper function to preprocess features and labels before training Decision Stump Model
def preprocess_features_before_training(features, labels):
    # 1. Reverse the feature and label set
    # 2. Scale the features to unit variance (except h2h feature). Also save the std. deviation of each feature
    # 3. Remove any duplicates (so we don't have any hard to find problems with dictionaries later
    x = features[::-1]
    y = labels[::-1]
    number_of_columns = x.shape[1] - 1

    # Before standardizing we want to take out the H2H column
    h2h = x[:, number_of_columns]

    # Delete this specific column
    x_shortened = np.delete(x, np.s_[-1], 1)

    standard_deviations = np.std(x_shortened, axis=0)

    # Center to the mean and component wise scale to unit variance.
    x_scaled = preprocessing.scale(x_shortened, with_mean=False)
    "Uncommented this line for taking out h2h feature"
    x_scaled = np.column_stack((x_scaled, h2h))  # Add H2H statistics back to the mix

    # We need to get rid of the duplicate values in our dataset. (Around 600 dups. Will check it later)
    x_scaled_no_duplicates, indices = np.unique(x_scaled, axis=0, return_index=True)
    y_no_duplicates = y[indices]

    return [x_scaled_no_duplicates, y_no_duplicates, standard_deviations]


"""
def google_cloud_upload():
   storage_client = storage.Client.from_service_account_json(
       'TennisPrediction-457d9e25f643.json')
   buckets = list(storage_client.list_buckets())
   print(buckets)
   Bucket_name = 'tennismodelbucket'
    bucket = storage_client.get_bucket(bucket_name)
    source_file_name = 'Local file to upload, for example ./file.txt'
    blob = bucket.blob(os.path.basename("stats.db"))

    # Upload the local file to Cloud Storage.
    blob.upload_from_filename(source_file_name)

    print('File {} uploaded to {}.'.format(
        source_file_name,
        bucket))"""


class Models(object):

    # TODO try gradient boosted regression trees. link: https://www.youtube.com/watch?v=IXZKgIsZRm0&t=892s
    # TODO XGBOOST, multi layered neural network

    def __init__(self, database_name):

        # Create a new pandas dataframe from the sqlite3 database we created
        conn = sqlite3.connect(database_name + '.db')

        # The name on this table should be the same as the dataframe
        dataset = pd.read_sql_query('SELECT * FROM updated_stats_v2', conn)

        # This changes all values to numeric if sqlite3 conversion gave a string
        dataset = dataset.apply(pd.to_numeric, errors='coerce')

        # Print statements to visually test some values
        dataset.dropna(subset=['SERVEADV1'], inplace=True)  # drop invalid stats (22)
        dataset.dropna(subset=['court_type'], inplace=True)  # drop invalid stats (616)
        dataset.dropna(subset=['H21H'], inplace=True)  # drop invalid stats (7)
        dataset.dropna(subset=['Number_of_games'], inplace=True)  # drop invalid stats (7)

        # Reset indexes after dropping N/A values
        dataset = dataset.reset_index(drop=True)  # reset indexes if any more rows are dropped
        dataset['year'].fillna(2018, inplace=True)
        dataset = dataset.reset_index(drop=True)  # reset indexes if any more rows are dropped
        print(dataset.isna().sum())

        self.dataset = dataset
        # Dictionaries for Decision Stump Model
        self.old_feature_label_dict = {}
        # A dictionary to map old_features (length 6-1D) to new_features (length 100 1-D)
        self.old_feature_to_new_feature_dictionary = defaultdict(list)
        self.new_feature_to_label_dictionary = {}
        # Only used for prediction mode
        self.predictions_old_feature_to_new_feature_dictionary = defaultdict(list)

    def create_feature_set(self, feature_set_name, label_set_name):
        # Takes the dataset created by FeatureExtraction and calculates required features for our model.
        # As of July 17: takes 90 minutes to complete the feature creation.
        common_more_than_5 = 0
        start_time = time.time()
        zero_common_opponents = 0
        x = []
        y = []
        court_dict = collections.defaultdict(dict)
        court_dict[1][1] = float(1)  # 1 is Hardcourt
        court_dict[1][2] = 0.28
        court_dict[1][3] = 0.35
        court_dict[1][4] = 0.24
        court_dict[1][5] = 0.24
        court_dict[1][6] = float(1)
        court_dict[2][1] = 0.28  # 2 is Clay
        court_dict[2][2] = float(1)
        court_dict[2][3] = 0.31
        court_dict[2][4] = 0.14
        court_dict[2][5] = 0.14
        court_dict[2][6] = 0.28
        court_dict[3][1] = 0.35  # 3 is Indoor
        court_dict[3][2] = 0.31
        court_dict[3][3] = float(1)
        court_dict[3][4] = 0.25
        court_dict[3][5] = 0.25
        court_dict[3][6] = 0.35
        court_dict[4][1] = 0.24  # 4 is carpet
        court_dict[4][2] = 0.14
        court_dict[4][3] = 0.25
        court_dict[4][4] = float(1)
        court_dict[4][5] = float(1)
        court_dict[4][6] = 0.24
        court_dict[5][1] = 0.24  # 5 is Grass
        court_dict[5][2] = 0.14
        court_dict[5][3] = 0.25
        court_dict[5][4] = float(1)
        court_dict[5][5] = float(1)
        court_dict[5][6] = 0.24
        court_dict[6][1] = float(1)  # 1 is Acyrlic
        court_dict[6][2] = 0.28
        court_dict[6][3] = 0.35
        court_dict[6][4] = 0.24
        court_dict[6][5] = 0.24
        court_dict[6][6] = float(1)

        # Bug Testing
        # code to check types of our stats dataset columns
        # with sqlite3.connect('stats.db', detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        #  show_deadline(conn, list(stats))

        # Start c
        for i in reversed(self.dataset.index):

            print(i)
            player1_id = self.dataset.at[i, "ID1"]
            player2_id = self.dataset.at[i, "ID2"]

            # All games that two players have played
            player1_games = self.dataset.loc[
                np.logical_or(self.dataset.ID1 == player1_id, self.dataset.ID2 == player1_id)]

            player2_games = self.dataset.loc[
                np.logical_or(self.dataset.ID1 == player2_id, self.dataset.ID2 == player2_id)]

            curr_tournament = self.dataset.at[i, "ID_T"]
            current_court_id = self.dataset.at[i, "court_type"]
            current_year = self.dataset.at[i, 'year']

            # Games played earlier than the current tournament we are investigating
            earlier_games_of_p1 = [game for game in player1_games.itertuples() if game.ID_T < curr_tournament]

            earlier_games_of_p2 = [game for game in player2_games.itertuples() if game.ID_T < curr_tournament]

            # Get past opponents of both players
            opponents_of_p1 = [games.ID2 if (player1_id == games.ID1) else games.ID1 for games in earlier_games_of_p1]

            opponents_of_p2 = [games.ID2 if (player2_id == games.ID1) else games.ID1 for games in earlier_games_of_p2]

            sa = set(opponents_of_p1)
            sb = set(opponents_of_p2)

            # Find common opponents that these players have faced
            common_opponents = sa.intersection(sb)

            if len(common_opponents) > 5:
                common_more_than_5 = common_more_than_5 + 1

            if len(common_opponents) == 0:
                zero_common_opponents = zero_common_opponents + 1
                # If they have zero common opponents, we cannot get features for this match
                continue

            else:
                # Find matches played against common opponents
                player1_games_updated = [game for opponent in common_opponents for game in earlier_games_of_p1 if
                                         (player1_id == game.ID1 and opponent == game.ID2) or (
                                                 player1_id == game.ID2 and opponent == game.ID1)]
                player2_games_updated = [game for opponent in common_opponents for game in earlier_games_of_p2 if
                                         (player2_id == game.ID1 and opponent == game.ID2) or (
                                                 player2_id == game.ID2 and opponent == game.ID1)]

                # Get the stats from those matches. Weighted by their surface matrix.
                list_of_serveadv_1 = [game.SERVEADV1 * court_dict[current_court_id][
                    game.court_type] if game.ID1 == player1_id else game.SERVEADV2 * court_dict[current_court_id][
                    game.court_type] for game in player1_games_updated]

                list_of_serveadv_2 = [game.SERVEADV1 * court_dict[current_court_id][
                    game.court_type] if game.ID1 == player2_id else game.SERVEADV2 * court_dict[current_court_id][
                    game.court_type] for game in player2_games_updated]

                list_of_complete_1 = [game.COMPLETE1 * court_dict[current_court_id][
                    game.court_type] if game.ID1 == player1_id else game.COMPLETE2 * court_dict[current_court_id][
                    game.court_type] for game in player1_games_updated]

                list_of_complete_2 = [game.COMPLETE1 * court_dict[current_court_id][
                    game.court_type] if game.ID1 == player2_id else game.COMPLETE2 * court_dict[current_court_id][
                    game.court_type] for game in player2_games_updated]

                list_of_w1sp_1 = [game.W1SP1 * court_dict[current_court_id][
                    game.court_type] if game.ID1 == player1_id else game.W1SP2 * court_dict[current_court_id][
                    game.court_type] for game in player1_games_updated]

                list_of_w1sp_2 = [game.W1SP1 * court_dict[current_court_id][game.court_type]
                                  if game.ID1 == player2_id else game.W1SP2 * court_dict[current_court_id][
                    game.court_type] for game in player2_games_updated]

                # ADDED: ACES PER GAME (NOT PER MATCH)
                list_of_aces_1 = [game.ACES_1 * court_dict[current_court_id][game.court_type] / game.Number_of_games
                                  if game.ID1 == player1_id else game.ACES_2 * court_dict[current_court_id][
                    game.court_type] / game.Number_of_games for game in player1_games_updated]

                list_of_aces_2 = [game.ACES_1 * court_dict[current_court_id][game.court_type] / game.Number_of_games
                                  if game.ID1 == player2_id else game.ACES_2 * court_dict[current_court_id][
                    game.court_type] / game.Number_of_games for game in player2_games_updated]

                # List of head to head statistics between two players
                list_of_h2h_1 = [game.H12H * court_dict[current_court_id][game.court_type]
                                 if game.ID1 == player1_id else game.H21H * court_dict[current_court_id][
                    game.court_type] for game in player1_games_updated]

                list_of_h2h_2 = [game.H12H * court_dict[current_court_id][game.court_type]
                                 if game.ID1 == player2_id else game.H21H * court_dict[current_court_id][
                    game.court_type] for game in player2_games_updated]

                list_of_tpw_1 = [game.TPWP1 * court_dict[current_court_id][game.court_type] / game.Number_of_games
                                 if game.ID1 == player1_id else game.TPWP2 * court_dict[current_court_id][
                    game.court_type] / game.Number_of_games for game in player1_games_updated]

                list_of_tpw_2 = [game.TPWP1 * court_dict[current_court_id][game.court_type] / game.Number_of_games
                                 if game.ID1 == player2_id else game.TPWP2 * court_dict[current_court_id][
                    game.court_type] / game.Number_of_games for game in player2_games_updated]

                serveadv_1 = s.mean(list_of_serveadv_1)
                serveadv_2 = s.mean(list_of_serveadv_2)
                complete_1 = s.mean(list_of_complete_1)
                complete_2 = s.mean(list_of_complete_2)
                w1sp_1 = s.mean(list_of_w1sp_1)
                w1sp_2 = s.mean(list_of_w1sp_2)
                aces_1 = s.mean(list_of_aces_1)  # Aces per game
                aces_2 = s.mean(list_of_aces_2)
                h2h_1 = s.mean(list_of_h2h_1)
                h2h_2 = s.mean(list_of_h2h_2)
                tpw1 = s.mean(list_of_tpw_1)  # Percentage of total points won
                tpw2 = s.mean(list_of_tpw_2)

                # The first feature of our feature set is the last match on the stats dataset
                if random() > 0.5:
                    # Player 1 has won. So we label it 1.
                    feature = np.array(
                        [serveadv_1 - serveadv_2, complete_1 - complete_2, w1sp_1 - w1sp_2, aces_1 - aces_2,
                         tpw1 - tpw2, h2h_1 - h2h_2])
                    label = 1

                    if np.any(np.isnan(feature)):
                        continue
                    else:
                        x.append(feature)
                        y.append(label)

                else:
                    # Else player 1 has lost, so we label it 0. Tht hope is that player 1 is chosen arbitrarily.
                    feature = np.array(
                        [serveadv_2 - serveadv_1, complete_2 - complete_1, w1sp_2 - w1sp_1, aces_2 - aces_1,
                         tpw2 - tpw1, h2h_2 - h2h_1])
                    label = 0
                    if np.any(np.isnan(feature)):
                        continue
                    else:
                        x.append(feature)
                        y.append(label)

        print("{} matches had more than 5 common opponents in the past".format(common_more_than_5))
        print("{} matches 0 common opponents in the past".format(zero_common_opponents))

        print("Time took for creating stat features for each match took--- %s seconds ---" % (time.time() - start_time))
        with open(feature_set_name, "wb") as fp:  # Pickling
            pickle.dump(x, fp)

        with open(label_set_name, "wb") as fp:  # Pickling
            pickle.dump(y, fp)

        return [x, y]

    def train_and_test_svm_model(self, model_name, dataset_name, labelset_name, dump, split):

        print("Training a new model {} on dataset {} and label set {}".format(model_name, dataset_name, labelset_name))

        start_time = time.time()

        pickle_in = open(dataset_name, "rb")
        data = np.asarray(pickle.load(pickle_in))
        pickle_in_2 = open(labelset_name, "rb")
        label = np.asarray(pickle.load(pickle_in_2))

        print("Size of our first dimension is {}.".format(np.size(data, 0)))
        print("Size of our second dimension is {}.".format(np.size(data, 1)))
        x = data[::-1]
        y = label[::-1]
        number_of_columns = x.shape[1] - 1

        # Before standardizing we want to take out the H2H column

        h2h = x[:, number_of_columns]

        # Delete this specific column
        x = np.delete(x, np.s_[-1], 1)

        # Center to the mean and component wise scale to unit variance.
        x_scaled = preprocessing.scale(x, with_mean=False)
        # x_scaled = np.column_stack((x_scaled, h2h))
        print(x_scaled.shape)
        x_train, x_test, y_train, y_test = train_test_split(x_scaled, y, test_size=split, shuffle=False)
        # Need the reverse the feature and labels because last match is the first feature in our array ??

        print(len(x_train))
        print(len(x_test))

        print("The standard deviations of our features is {}.".format(np.std(x_train, axis=0)))
        print("The means of our features is {}.".format(np.mean(x_train, axis=0)))

        # Create and train the model
        clf = svm.NuSVC()
        clf.fit(x_train, y_train)

        # Testing the model

        print("Training accuracy for {} on {} and {} is: {}".format(model_name, dataset_name, labelset_name,
                                                                    clf.score(x_train, y_train)))

        print("Testing accuracy for {} on {} and {} is: {}".format(model_name, dataset_name, labelset_name,
                                                                   clf.score(x_test, y_test)))

        print("Time took for training and testing the model took--- %s seconds ---" % (time.time() - start_time))

        # now we save the model to a file if test were successful
        if (dump):
            joblib.dump(clf, model_name)

    def train_decision_stump_model(self, dataset_name, labelset_name, development_mode, prediction_mode, save):

        pickle_in = open(dataset_name, "rb")
        features = np.asarray(pickle.load(pickle_in))
        pickle_in_2 = open(labelset_name, "rb")
        labels = np.asarray(pickle.load(pickle_in_2))

        # Preprocess the feature and label space
        x_scaled_no_duplicates, y_no_duplicates, standard_deviations = preprocess_features_before_training(features,
                                                                                                           labels)
        print("Size of our first dimension is {}.".format(np.size(x_scaled_no_duplicates, 0)))
        print("Size of our second dimension is {}.".format(np.size(x_scaled_no_duplicates, 1)))
        print("The number of UNIQUE features in our feature space is {}".format(len(x_scaled_no_duplicates)))
        print("New label set size must be {}.".format(len(y_no_duplicates)))

        # dict of tuple (6D np array --> label)
        self.old_feature_label_dict = {tuple(x_scaled_no_duplicates[x]): y_no_duplicates[x] for x in
                                       range(len(x_scaled_no_duplicates))}

        print("Our final set includes {} features".format(len(self.old_feature_label_dict)))

        for feat in x_scaled_no_duplicates:
            assert tuple(feat) in self.old_feature_label_dict

        if development_mode:
            # This mode is used for hyperparameter optimization
            x_tr, x_test, y_tr, y_test = train_test_split(x_scaled_no_duplicates, y_no_duplicates, test_size=0.2,
                                                          shuffle=False)

            x_train, x_dev, y_train, y_dev = train_test_split(x_tr, y_tr, test_size=0.2, shuffle=False)

            print("Size of the training set is: {}.".format((len(x_train))))
            print("Size of the dev set is: {}.".format((len(x_dev))))
            print("Size of the dev set is: {}.".format((len(x_test))))

            assert len(x_train) + len(x_dev) + len(x_test) == len(x_scaled_no_duplicates)

            # WARNING: BLOWING UP THE FEATURE SPACE
            self.create_100_decision_stumps(x_train, y_train, x_scaled_no_duplicates, 0.5)

            # these are the new feature and label set we will training SGD Classifier
            decision_stump_features, decision_stump_labels = self.create_new_vector_label_dataset(
                self.old_feature_to_new_feature_dictionary)

            # Testing data turned into this format
            test_data = np.asarray([self.old_feature_to_new_feature_dictionary[tuple(x)] for x in x_test])
            test_label = np.asarray([self.old_feature_label_dict[tuple(x)] for x in x_test])

            # Development data to 100 length 1d vector
            dev_data = np.asarray([self.old_feature_to_new_feature_dictionary[tuple(x)] for x in x_dev])
            dev_label = np.asarray([self.old_feature_label_dict[tuple(x)] for x in x_dev])

            # Function to tune SGD Hyperparameters using development data.
            tune_sgd_hyperparameters(decision_stump_features, decision_stump_labels, dev_data, dev_label)

            # Even in development mode, we do some testing.
            linear_clf = SGDClassifier(loss="hinge", eta0=0.0001)  # create the tuned classifier
            linear_clf.fit(decision_stump_features, decision_stump_labels)

            print("Linear SGD classifier training accuracy {}.".format(
                linear_clf.score(decision_stump_features, decision_stump_labels)))
            print("Linear SGD classifier testing accuracy {}.".format(linear_clf.score(test_data, test_label)))

        if prediction_mode:

            p1_list = [19, 655, 7806, 961, 4061, 2123, 678, 791, 6101, 18094, 9831, 5837, 10995, 30470, 4454,
                       4009, 650,
                       20847, 6458, 22434, 11522, 13447, 29932, 6465, 12043, 29812, 1113, 17829, 3833, 39309, 9043,
                       19, 7806, 4061, 678, 9471, 2706, 5837, 30470, 25543, 20847, 22434, 6848, 6465, 4010, 18017,
                       39309, 19, 5917, 18094, 5837, 25543, 8806, 6465, 18017]
            p2_list = [5127, 14177, 12661, 22807, 1266, 5917, 685, 7459, 9471, 27482, 11704, 9840, 10828, 26923,
                       1092, 25543,
                       29939, 11003, 5992, 6081, 8806, 6848, 24008, 468, 33502, 4010, 9521, 18017, 4067, 14727, 677,
                       14177, 22807, 5917, 7459, 18094, 11704, 10828, 4454, 29939, 5992, 8806, 24008, 12043, 9521, 4067,
                       677, 7806, 7459, 11704, 30470, 5992, 6848, 4010, 677]
            results = [1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0,
                       1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0]

            assert len(p1_list) == len(p2_list) == len(results)
            # DONT FORGET: IF PLAYERS DO NOT HAVE COMMON OPPONENTS, YOU HAVE TO DELETE THAT RESULT FROM THE SET. PLAYERS AS WELL

            del p1_list[36]
            del p2_list[36]
            del results[36]

            index_games_dict_for_prediction = {tuple(self.make_predictions_using_DT(p1, p2, 5, 15300)): [p1, p2] for
                                               i, (p1, p2) in enumerate(zip(p1_list, p2_list))}
            features_from_prediction = np.asarray(
                [np.asarray(feature) for feature in index_games_dict_for_prediction.keys()])

            # Scale the features with the standard deviations of our dataset.
            features_from_prediction_final = preprocess_features_of_predictions(features_from_prediction,
                                                                                standard_deviations)
            assert len(features_from_prediction_final) == len(index_games_dict_for_prediction)
            temporary = features_from_prediction_final.tolist()
            # This dictionary ties last version of features to player id's
            features_match_dictionary = {tuple(temporary[i]): v for i, (k, v) in
                                         enumerate(index_games_dict_for_prediction.items())}

            # WARNING: BLOWING UP THE FEATURE SPACE
            self.create_100_decision_stumps_include_predictions(x_scaled_no_duplicates, y_no_duplicates,
                                                                x_scaled_no_duplicates, 0.5,
                                                                features_from_prediction_final)

            # these are the new feature and label set we will training SGD Classifier
            decision_stump_features, decision_stump_labels = self.create_new_vector_label_dataset(
                self.old_feature_to_new_feature_dictionary)
            print("Length of old_feature_to_new_feature_dictionary is {},".format(
                len(self.old_feature_to_new_feature_dictionary)))

            linear_clf = SGDClassifier(loss="hinge", eta0=0.0001)  # create the tuned classifier
            linear_clf.fit(decision_stump_features, decision_stump_labels)

            print("Linear SGD classifier training accuracy {}.".format(
                linear_clf.score(decision_stump_features, decision_stump_labels)))

            games = np.asarray(
                [np.asarray(feature) for feature in self.predictions_old_feature_to_new_feature_dictionary.values()])
            actual_labels = np.asarray(results)

            print("Wimbledon Round 2,3,4 Accuracy is {}.".format(linear_clf.score(games, actual_labels)))
            for (old_test_vector, new_test_vector) in self.predictions_old_feature_to_new_feature_dictionary.items():
                print("Prediction for match {} was {}.".format(features_match_dictionary[tuple(old_test_vector)],
                                                               linear_clf.predict(
                                                                   np.asarray(new_test_vector).reshape(1, -1))))
            if save:
                joblib.dump(linear_clf, 'DT_Model_3.pkl')
        else:

            # We want to train our model and test its training and testing accuracy
            x_train, x_test, y_train, y_test = train_test_split(x_scaled_no_duplicates, y_no_duplicates, test_size=0.2,
                                                                shuffle=False)
            print("Size of the training set is: {}.".format((len(x_train))))
            print("Size of the test set is: {}.".format((len(x_test))))

            assert len(x_train) + len(x_test) == len(x_scaled_no_duplicates)

            # WARNING: BLOWING UP THE FEATURE SPACE
            self.create_100_decision_stumps(x_train, y_train, x_scaled_no_duplicates, 0.5)  # create DT stumps

            # these are the new feature and label set we will training SGD Classifier
            decision_stump_features, decision_stump_labels = self.create_new_vector_label_dataset(
                self.old_feature_to_new_feature_dictionary)

            # creating 100 1d vectors from our test dataset
            test_data = np.asarray([self.old_feature_to_new_feature_dictionary[tuple(x)] for x in x_test])
            test_label = np.asarray([self.old_feature_label_dict[tuple(x)] for x in x_test])

            linear_clf = SGDClassifier(loss="hinge", eta0=0.0001)  # create the tuned classifier
            linear_clf.fit(decision_stump_features, decision_stump_labels)

            print("Linear SGD classifier training accuracy {}.".format(
                linear_clf.score(decision_stump_features, decision_stump_labels)))
            print("Linear SGD classifier testing accuracy {}.".format(linear_clf.score(test_data, test_label)))

            if save:
                joblib.dump(linear_clf, 'DT_Model_2_no_h2h.pkl')

    def create_100_decision_stumps_include_predictions(self, x, y, whole_training_set, test_size, predictions):
        for i in range(100):
            start_time = time.time()

            data_train, data_test, labels_train, labels_test = train_test_split(x, y, test_size=test_size, shuffle=True)
            # train a Decision Stump - Classifier

            clf = tree.DecisionTreeClassifier(max_depth=8)
            clf.fit(data_train, labels_train)

            for data_point in whole_training_set:
                # for each data point in the whole set, predict its label
                predicted_label = clf.predict(data_point.reshape(1, -1))

                # add the predicted label to the list which is mapped to its data_point
                # dict: tuple of 6D np array to 100D np array
                self.old_feature_to_new_feature_dictionary[tuple(data_point)].append(predicted_label[0])

            for prediction in predictions:
                predicted_label = clf.predict(prediction.reshape(1, -1))
                self.predictions_old_feature_to_new_feature_dictionary[tuple(prediction)].append(predicted_label[0])

            print("Time took to train decision stump number {} and make predictions was --- {} seconds ---".format(i,
                                                                                                                   time.time() - start_time))

    def create_100_decision_stumps(self, x, y, whole_training_set, test_size):
        # Now we create and train 100 Decision Stumps.
        # Then predict label of each data point in four fold files (560 data points) and store them in a {vector: label list} dictionary
        for i in range(100):
            start_time = time.time()

            data_train, data_test, labels_train, labels_test = train_test_split(x, y, test_size=test_size, shuffle=True)
            # train a Decision Stump - Classifier

            clf = tree.DecisionTreeClassifier(max_depth=8)
            clf.fit(data_train, labels_train)

            for data_point in whole_training_set:
                # for each data point in the whole set, predict its label
                predicted_label = clf.predict(data_point.reshape(1, -1))

                # add the predicted label to the list which is mapped to its data_point
                # dict: tuple of 6D np array to 100D np array
                self.old_feature_to_new_feature_dictionary[tuple(data_point)].append(predicted_label[0])
            print("Time took to train decision stump number {} and make predictions was --- {} seconds ---".format(i,
                                                                                                                   time.time() - start_time))

    def create_new_vector_label_dataset(self, old_new_feature_dict):

        # Functions associates new 100-1D vectors with their correct labels
        X = []
        y = []
        for old_feature, new_feature in old_new_feature_dict.items():
            X.append(list(new_feature))
            y.append(self.old_feature_label_dict[old_feature])

        X = np.array(X)
        y = np.array(y)
        return [X, y]

    def make_predictions_using_DT(self, player1_id, player2_id, current_court_id, curr_tournament):

        court_dict = collections.defaultdict(dict)
        court_dict[1][1] = float(1)  # 1 is Hardcourt
        court_dict[1][2] = 0.28
        court_dict[1][3] = 0.35
        court_dict[1][4] = 0.24
        court_dict[1][5] = 0.24
        court_dict[1][6] = float(1)
        court_dict[2][1] = 0.28  # 2 is Clay
        court_dict[2][2] = float(1)
        court_dict[2][3] = 0.31
        court_dict[2][4] = 0.14
        court_dict[2][5] = 0.14
        court_dict[2][6] = 0.28
        court_dict[3][1] = 0.35  # 3 is Indoor
        court_dict[3][2] = 0.31
        court_dict[3][3] = float(1)
        court_dict[3][4] = 0.25
        court_dict[3][5] = 0.25
        court_dict[3][6] = 0.35
        court_dict[4][1] = 0.24  # 4 is carpet
        court_dict[4][2] = 0.14
        court_dict[4][3] = 0.25
        court_dict[4][4] = float(1)
        court_dict[4][5] = float(1)
        court_dict[4][6] = 0.24
        court_dict[5][1] = 0.24  # 5 is Grass
        court_dict[5][2] = 0.14
        court_dict[5][3] = 0.25
        court_dict[5][4] = float(1)
        court_dict[5][5] = float(1)
        court_dict[5][6] = 0.24
        court_dict[6][1] = float(1)  # 1 is Acyrlic
        court_dict[6][2] = 0.28
        court_dict[6][3] = 0.35
        court_dict[6][4] = 0.24
        court_dict[6][5] = 0.24
        court_dict[6][6] = float(1)

        # All games that two players have played
        player1_games = self.dataset.loc[np.logical_or(self.dataset.ID1 == player1_id, self.dataset.ID2 == player1_id)]

        player2_games = self.dataset.loc[np.logical_or(self.dataset.ID1 == player2_id, self.dataset.ID2 == player2_id)]

        # This value should be higher than anything else curr_tournament = dataset.at[i, "ID_T"]
        earlier_games_of_p1 = [game for game in player1_games.itertuples() if
                               game.ID_T < curr_tournament]

        earlier_games_of_p2 = [game for game in player2_games.itertuples() if
                               game.ID_T < curr_tournament]

        opponents_of_p1 = [
            games.ID2 if (player1_id == games.ID1) else
            games.ID1 for games in earlier_games_of_p1]

        opponents_of_p2 = [
            games.ID2 if (player2_id == games.ID1) else
            games.ID1 for games in earlier_games_of_p2]

        sa = set(opponents_of_p1)
        sb = set(opponents_of_p2)

        # Find common opponents that these players have faced
        common_opponents = sa.intersection(sb)

        if len(common_opponents) > 5:

            player1_games_updated = [game for opponent in common_opponents for game in earlier_games_of_p1 if
                                     (player1_id == game.ID1 and opponent == game.ID2) or (
                                             player1_id == game.ID2 and opponent == game.ID1)]
            player2_games_updated = [game for opponent in common_opponents for game in earlier_games_of_p2 if
                                     (player2_id == game.ID1 and opponent == game.ID2) or (
                                             player2_id == game.ID2 and opponent == game.ID1)]

            list_of_serveadv_1 = [game.SERVEADV1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player1_id else game.SERVEADV2 * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_serveadv_2 = [game.SERVEADV1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player2_id else game.SERVEADV2 * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_complete_1 = [game.COMPLETE1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player1_id else game.COMPLETE2 * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_complete_2 = [game.COMPLETE1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player2_id else game.COMPLETE2 * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_w1sp_1 = [game.W1SP1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player1_id else game.W1SP2 * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_w1sp_2 = [game.W1SP1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player2_id else game.W1SP2 * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_aces_1 = [game.ACES_1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player1_id else game.ACES_2 * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_aces_2 = [game.ACES_1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player2_id else game.ACES_2 * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_h2h_1 = [game.H12H * court_dict[current_court_id][game.court_type]
                             if game.ID1 == player1_id else game.H21H * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_h2h_2 = [game.H12H * court_dict[current_court_id][game.court_type]
                             if game.ID1 == player2_id else game.H21H * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_tpw_1 = [game.TPWP1 * court_dict[current_court_id][game.court_type] / game.Number_of_games
                             if game.ID1 == player1_id else game.TPWP2 * court_dict[current_court_id][
                game.court_type] / game.Number_of_games for game in player1_games_updated]

            list_of_tpw_2 = [game.TPWP1 * court_dict[current_court_id][game.court_type] / game.Number_of_games
                             if game.ID1 == player2_id else game.TPWP2 * court_dict[current_court_id][
                game.court_type] / game.Number_of_games for game in player2_games_updated]

            serveadv_1 = s.mean(list_of_serveadv_1)
            serveadv_2 = s.mean(list_of_serveadv_2)
            complete_1 = s.mean(list_of_complete_1)
            complete_2 = s.mean(list_of_complete_2)
            w1sp_1 = s.mean(list_of_w1sp_1)
            w1sp_2 = s.mean(list_of_w1sp_2)
            aces_1 = s.mean(list_of_aces_1)
            aces_2 = s.mean(list_of_aces_2)
            h2h_1 = s.mean(list_of_h2h_1)
            h2h_2 = s.mean(list_of_h2h_2)
            tpw1 = s.mean(list_of_tpw_1)  # Percentage of total points won
            tpw2 = s.mean(list_of_tpw_2)
            feature = np.array(
                [serveadv_1 - serveadv_2, complete_1 - complete_2, w1sp_1 - w1sp_2, aces_1 - aces_2, tpw1 - tpw2,
                 h2h_1 - h2h_2])
            return feature
        else:
            print("The players {} and {} do not have enough common opponents to make predictions".format(player1_id,
                                                                                                         player2_id))
            return np.zeros([6, ])

    def make_predictions_using_SVM(self, model_name, player1_id, player2_id, current_court_id, curr_tournament):
        clf = joblib.load(model_name)

        court_dict = collections.defaultdict(dict)
        court_dict[1][1] = float(1)  # 1 is Hardcourt
        court_dict[1][2] = 0.28
        court_dict[1][3] = 0.35
        court_dict[1][4] = 0.24
        court_dict[1][5] = 0.24
        court_dict[1][6] = float(1)

        court_dict[2][1] = 0.28  # 2 is Clay
        court_dict[2][2] = float(1)
        court_dict[2][3] = 0.31
        court_dict[2][4] = 0.14
        court_dict[2][5] = 0.14
        court_dict[2][6] = 0.28
        court_dict[3][1] = 0.35  # 3 is Indoor
        court_dict[3][2] = 0.31
        court_dict[3][3] = float(1)
        court_dict[3][4] = 0.25
        court_dict[3][5] = 0.25
        court_dict[3][6] = 0.35
        court_dict[4][1] = 0.24  # 4 is carpet
        court_dict[4][2] = 0.14
        court_dict[4][3] = 0.25
        court_dict[4][4] = float(1)
        court_dict[4][5] = float(1)
        court_dict[4][6] = 0.24
        court_dict[5][1] = 0.24  # 5 is Grass
        court_dict[5][2] = 0.14
        court_dict[5][3] = 0.25
        court_dict[5][4] = float(1)
        court_dict[5][5] = float(1)
        court_dict[5][6] = 0.24
        court_dict[6][1] = float(1)  # 1 is Acyrlic
        court_dict[6][2] = 0.28
        court_dict[6][3] = 0.35
        court_dict[6][4] = 0.24
        court_dict[6][5] = 0.24
        court_dict[6][6] = float(1)

        # All games that two players have played
        player1_games = self.dataset.loc[np.logical_or(self.dataset.ID1 == player1_id, self.dataset.ID2 == player1_id)]

        player2_games = self.dataset.loc[np.logical_or(self.dataset.ID1 == player2_id, self.dataset.ID2 == player2_id)]

        # This value should be higher than anything else curr_tournament = dataset.at[i, "ID_T"]
        earlier_games_of_p1 = [game for game in player1_games.itertuples() if
                               game.ID_T < curr_tournament]

        earlier_games_of_p2 = [game for game in player2_games.itertuples() if
                               game.ID_T < curr_tournament]

        opponents_of_p1 = [
            games.ID2 if (player1_id == games.ID1) else
            games.ID1 for games in earlier_games_of_p1]

        opponents_of_p2 = [
            games.ID2 if (player2_id == games.ID1) else
            games.ID1 for games in earlier_games_of_p2]

        sa = set(opponents_of_p1)
        sb = set(opponents_of_p2)

        # Find common opponents that these players have faced
        common_opponents = sa.intersection(sb)

        if len(common_opponents) > 5:
            print("These players have more than 5 common opponents ")

            player1_games_updated = [game for opponent in common_opponents for game in earlier_games_of_p1 if
                                     (player1_id == game.ID1 and opponent == game.ID2) or (
                                             player1_id == game.ID2 and opponent == game.ID1)]
            player2_games_updated = [game for opponent in common_opponents for game in earlier_games_of_p2 if
                                     (player2_id == game.ID1 and opponent == game.ID2) or (
                                             player2_id == game.ID2 and opponent == game.ID1)]

            list_of_serveadv_1 = [game.SERVEADV1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player1_id else game.SERVEADV2 * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_serveadv_2 = [game.SERVEADV1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player2_id else game.SERVEADV2 * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_complete_1 = [game.COMPLETE1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player1_id else game.COMPLETE2 * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_complete_2 = [game.COMPLETE1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player2_id else game.COMPLETE2 * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_w1sp_1 = [game.W1SP1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player1_id else game.W1SP2 * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_w1sp_2 = [game.W1SP1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player2_id else game.W1SP2 * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_aces_1 = [game.ACES_1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player1_id else game.ACES_2 * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_aces_2 = [game.ACES_1 * court_dict[current_court_id][
                game.court_type] if game.ID1 == player2_id else game.ACES_2 * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_h2h_1 = [game.H12H * court_dict[current_court_id][game.court_type]
                             if game.ID1 == player1_id else game.H21H * court_dict[current_court_id][
                game.court_type] for game in player1_games_updated]

            list_of_h2h_2 = [game.H12H * court_dict[current_court_id][game.court_type]
                             if game.ID1 == player2_id else game.H21H * court_dict[current_court_id][
                game.court_type] for game in player2_games_updated]

            list_of_tpw_1 = [game.TPWP1 * court_dict[current_court_id][game.court_type] / game.Number_of_games
                             if game.ID1 == player1_id else game.TPWP2 * court_dict[current_court_id][
                game.court_type] / game.Number_of_games for game in player1_games_updated]

            list_of_tpw_2 = [game.TPWP1 * court_dict[current_court_id][game.court_type] / game.Number_of_games
                             if game.ID1 == player2_id else game.TPWP2 * court_dict[current_court_id][
                game.court_type] / game.Number_of_games for game in player2_games_updated]

            serveadv_1 = s.mean(list_of_serveadv_1)
            serveadv_2 = s.mean(list_of_serveadv_2)
            complete_1 = s.mean(list_of_complete_1)
            complete_2 = s.mean(list_of_complete_2)
            w1sp_1 = s.mean(list_of_w1sp_1)
            w1sp_2 = s.mean(list_of_w1sp_2)
            aces_1 = s.mean(list_of_aces_1)
            aces_2 = s.mean(list_of_aces_2)
            h2h_1 = s.mean(list_of_h2h_1)
            h2h_2 = s.mean(list_of_h2h_2)
            tpw1 = s.mean(list_of_tpw_1)  # Percentage of total points won
            tpw2 = s.mean(list_of_tpw_2)
            feature = np.array(
                [serveadv_1 - serveadv_2, complete_1 - complete_2, w1sp_1 - w1sp_2, aces_1 - aces_2, tpw1 - tpw2,
                 h2h_1 - h2h_2])

            print("The prediction between player {} and player {} is {}".format(player1_id, player2_id, clf.predict(
                np.array(feature).reshape(1, -1))))



        else:
            print("These players do not have enough common opponents to make predictions")
            return


DT = Models("updated_stats_v2")

# To create the feature and label space
# data_label = DT.create_feature_set('data_tpw_h2h.txt', 'label_tpw_h2h.txt')
# print(len(data_label[0]))
# print(len(data_label[1]))

# To create an SVM Model
# DT.train_and_test_svm_model("svm_model_tpw_no_h2h.pkl", 'data_tpw_h2h.txt', 'label_tpw_h2h.txt', True, 0.2)
DT.train_decision_stump_model('data_tpw_h2h.txt', 'label_tpw_h2h.txt', development_mode=False, prediction_mode=True,
                              save=True)
# To test the model
# test_model("svm_model_v4_h2h.pkl", "data_with_h2h.txt", "label_with_h2h.txt", 0.2)
# test_model("svm_model_v3.pkl", "data_v3.txt", "label_v3.txt", 0.2)


"""  clf_1 = svm.NuSVC()
    visualizer = ClassificationReport(clf_1)
    visualizer.fit(train_X, train_Y)  # Fit the visualizer and the model
    visualizer.score(test_X, test_Y)  # Evaluate the model on the test data
    g = visualizer.poof()  # Draw/show/poof the data"""
"""
# Wimbledon Round 2
 p1_list = [19, 655, 7806, 961, 4061, 2123, 678, 791, 6101, 18094, 9831, 5837, 10995, 30470, 4454,
                       4009, 650,
                       20847, 6458, 22434, 11522, 13447, 29932, 6465, 12043, 29812, 1113, 17829, 3833, 39309, 9043]
p2_list = [5127, 14177, 12661, 22807, 1266, 5917, 685, 7459, 9471, 27482, 11704, 9840, 10828, 26923,
                       1092, 25543,
                       29939, 11003, 5992, 6081, 8806, 6848, 24008, 468, 33502, 4010, 9521, 18017, 4067, 14727, 677]
results = [1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0]
The players 20193 and 2706 do not have enough common opponents to make predictions. Novak vs Pouille 
assert len(p1_list) == len(p2_list) == len(results)
"""
"""
# Wimbledon Round 3
p1_list = [19, 7806, 4061, 678, 9471, 2706, 5837, 30470, 25543, 20847, 22434, 6848, 6465, 4010, 18017, 39309]
p2_list = [14177, 22807, 5917, 7459, 18094, 11704, 10828, 4454, 29939, 5992, 8806, 24008, 12043, 9521, 4067, 677]
results = [1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 0]
assert len(p1_list) == len(p2_list) == len(results)

# Wimbledon Round 4
p1_list = [19, 5917, 18094, 5837, 25543, 8806, 6465, 18017]
p2_list = [7806, 7459, 11704, 30470, 5992, 6848, 4010, 677]
results = [1, 0, 0, 1, 0, 1, 1, 0]
assert len(p1_list) == len(p2_list) == len(results)

# Wimbledon Quarter Finals + Semi Finals
p1_list = [19,11704,5992,6465,7459,5992] 
p2_list = [7459,5837,8806,677,5837,677] 
results = [0,0,1,0,1,1]
assert len(p1_list) == len(p2_list) == len(results)
"""