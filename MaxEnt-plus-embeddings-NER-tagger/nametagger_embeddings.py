#!/usr/bin/env python3

# Leslie Huang (LH1036)
# Natural Language Processing Assignment 7
# April 12, 2018

import argparse
import collections
import itertools
import sys
from geotext import GeoText
from nltk.classify import MaxentClassifier
from nltk.corpus import names
from nltk.corpus import stopwords

###########################################################
### Helper functions to format training/test data ###
###########################################################

def split_raw_data(raw_data):
    """
    Helper function to convert raw data
    Args:
        raw_data: Test or training data read into [str]
    Returns:
        [ [token, pos, ...], "\n", ] "\n" indicates boundary between "sentences"

    """
    return [
        line if line == "\n"
        else line.split("\t")
        for line in raw_data
    ]

def group_features_by_sentence(raw_data_split):
    """
    Group words into sentences (sentence = [token, ...]) and removes str "\n" boundary
    Args:
        raw_data_split: List whose elements are features w/ tags
    Returns:
        List of lists, where each list contains words from a sentence.
    """
    sentences_list = []
    for _, g in itertools.groupby(raw_data_split, lambda x: x == "\n"):
        sentences_list.append(list(g)) # Store group iterator as a list

    return [g for g in sentences_list if g not in [["\n"], ["\n", "\n"]] ]


def feature_dict(feature_vector):
    """
    Converts [feature vector] into {Dict of features}
    Args:
        feature vector : in the format [token, pos, chunk, ...]
    Returns:
        {Dict of features }
    """
    return {
        "token": feature_vector[0],
        "pos": feature_vector[1],
        "chunk": feature_vector[2].strip(),
    }

def extract_features_dict(sentence):
    """
    Apply feature_dict to all feature_vectors in a sentence
    Args:
        sentence: [ [feature_vector], [feature_vector], ... ] where each feature_vector corresponds to a token
    Returns:
        [ {Dict of features}, {Dict of features}]
    """
    return [feature_dict(feature_vector) for feature_vector in sentence]

def extract_labels(sentence):
    """
    Extract label (name) from training data by sentence
    Args:
        sentence: [ [feature_vector], [feature_vector], ... ] where each feature_vector corresponds to a token
            and 4th element (if it exists) is the named entity label for that feature
    Returns:
        [str of feature labels]
    """
    return [feature_vector[3].strip() for feature_vector in sentence ]

def extract_orig_tokens(raw_data_split):
    """
    Takes raw_data_split and returns only the original tokens, with "\n" preserved.
    Args:
        raw_data_split: generated by split_raw_data()
    Returns:
        [token, "\n", token ... ] : elements are tokens as str, with "\n" separating sentences.
            Input for generating tagged output of test/dev data
    """
    return [
            line if line == "\n"
            else line[0]
            for line in raw_data_split
        ]


###########################################################
### Helper functions for adding sentence-level features ###
###########################################################

def add_sentence_position(sentence):
        """
        Adds sentence position key-value pairs to tokens in a single [sentence]
        Args:
            sentence: [{Dict of features},... ] with each element corresponding to a token in the sentence
        Returns:
            sentence with new key-value for token position in sentence
        """
        for counter, value in enumerate(sentence):
            value["token_position"] = counter

        return sentence

def add_sentence_boundaries(sentence):
    """
    Add key-value pairs for start and end tokens. ** Must be run after add_sentence_position() **
    Args:
        sentence: [{Dict of features},... ] with each element corresponding to a token in the sentence
    Returns:
        sentence with new key-values for start and end tokens
    """
    for feature in sentence:
        feature["start_token"] = feature["token_position"] == 0
        feature["end_token"] = feature["token_position"] == len(sentence) - 1

    return sentence

def add_prior_future_n_states(sentence, n):
    """
    Add features for previous token and next token at distances of [1, n] tokens
    Args:
        n: max distance of token window from a given token
        sentence: [{Dict of features},... ] with each element corresponding to a token in the sentence
    Returns:
        sentence with new key-value pairs for all prev_tokens and next_tokens within the range of n.
        Value of key is None if token does not exist in that window
    """
    for i in range(1, n+1):
        for feature in sentence:
            current_position = feature["token_position"]
            if feature["token_position"] - i >= 0:
                feature["prev_token_{}".format(i)] = sentence[current_position - i]["token"]
            else:
                feature["prev_token_{}".format(i)] = None

            if feature["token_position"] + n < len(sentence):
                feature["next_token_{}".format(i)] = sentence[current_position + i]["token"]
            else:
                feature["next_token_{}".format(i)] = None

    return sentence


###########################################################
###########################################################

### GloveModel helper functions ###
###########################################################

def separate_words_dims(raw_data):
    """
    Helper function to extract list of words and list of lists of dimensions
    Args:
        raw_data: raw data read in from trained vectors file
    Returns:
        words: list of words in order
        dims: list of lists of dimensions corresponding to the words
    """
    num_dims = len(raw_data[0])
    words = []
    dims = []

    for line in raw_data:
        words.append(line[0]) # first elem in each list is the word
        dims.append(line[1:num_dims]) # elem 1:n in each list are the dimensions values

    return words, dims

def create_dimensions_dict(dimensions_vector):
    """
    Creates a dimensions_dict from a dimensions_vector
    Args:
        dimensions_vect [list of floats]
    Returns:
        dimensions_dict of sequentially numbered keys and values from dimensions_vect
        e.g. {"1": float, "2": float, ...}

    """
    return {
        counter: value
        for counter, value in enumerate(dimensions_vector)
    }

def word_vector_dicts(words, dims):
    """
    Creates {word: dimensions_dict} from a word and a dimensions_vector
    Args:
        words: [list of words as str]
        dims: [list of dimensions_vectors, which are themselves lists]
    Returns:
        {word1: {dimensions_dict1}, word2: {dimensions_dict2}, ...}
    """
    return {
                word: create_dimensions_dict(dimensions_vector)
        for word, dimensions_vector in zip(words, dims)
    }



###########################################################
###########################################################
### Class for GLOVE trained word vectors ###
###########################################################

class GloveModel:

    def __init__(self, filepath):
        """
        """
        self.filepath = filepath
        self.trained_vector = None

        self.load_trained_vectors()


    def load_trained_vectors(self):
        with open(self.filepath, "r") as f:
            f.readlines()


###########################################################
###########################################################

class FeatureBuilder:
    def __init__(self, filepath, is_training):
        self.filepath = filepath
        self.is_training = is_training

        self.sentences_features_dicts = None # temporary data with sentence structure in place, used to generate features for self.features
        self.features = None
        self.labels = None # will be populated for training data
        self.orig_data = None # for output of test/dev data

        self.load()

    def load(self):
        """
        Load training or test data and populate self.features, self.labels, and self.orig_data
        Returns:
            Data converted into test/training format for MaxEnt
        """
        with open(self.filepath, "r") as f:
            raw_data = f.readlines()

        split_data = split_raw_data(raw_data)

        self.extract_features_dicts_by_sentence(split_data)
        self.extract_labels(split_data)
        self.extract_orig_data(split_data)


    def extract_features_dicts_by_sentence(self, split_data):
        """
        Converts data from split_raw_data() to format for self.sentences_features_dicts
        Args:
            split_data: raw data that has gone through split_raw_data()
        Returns:
            List of lists of feature dicts (sentence structure is still preserved, each inner list represents one sentence)
        """
        features_grouped = group_features_by_sentence(split_data)

        self.sentences_features_dicts = [extract_features_dict(sentence) for sentence in features_grouped]


    def extract_labels(self, split_data):
        """
        Extracts list of named entity labels from training data to populate self.labels
        Args:
            split_data: raw data that has gone through split_raw_data()
        Returns:
            [nametag] in a flat list
        """
        features_grouped = group_features_by_sentence(split_data)

        if self.is_training:
            labels = [extract_labels(sentence) for sentence in features_grouped]
            # need to flatten out the structure of sentences within the larger list, because features list will also be flattened
            self.labels = list(itertools.chain.from_iterable(labels))


    def extract_orig_data(self, split_data):
        """
        Populates self.orig_data if it is test/dev data
        Args:
            split_data : [ [token, pos, ...], "\n", ] where "\n" indicates boundary between "sentences"
        Returns:
            Populates self.orig_data with [str] containing just tokens and "\n" between sentences
        """
        if not self.is_training:
            self.orig_data = extract_orig_tokens(split_data)


    def format_data_maxent(self):
        """
        Generates properly formatted training data for NLTK's MaxEnt
        Returns:
            [ ({feature_dict}, nametag), ...]
        """
        return list(zip(self.features, self.labels))

    ##########################################################
    ### Sentence-level features ###
    ##########################################################


    def add_sentence_features(self):
        """
        Add key-value pairs for token position in sentence (position #, start, end), from sentences_features_dicts
        Returns:
            Populates self.features with [{features_dicts}] with each element representing a token in the raw data
        """
        features_dicts = []
        for sentence in self.sentences_features_dicts:
            sentence = add_sentence_position(sentence)
            sentence = add_sentence_boundaries(sentence)
            sentence = add_prior_future_n_states(sentence, 1)
            features_dicts.append(sentence)

        self.features = list(itertools.chain.from_iterable(features_dicts)) # flatten the List-of-Lists structure


    ##########################################################
    ## Token-level features                                ###
    ##########################################################

    def add_case(self, features_dict):
        features_dict["case"] = "lower" if features_dict["token"] == features_dict["token"].lower() else "upper"

    def add_last_char(self, features_dict):
        features_dict["last_char"] = features_dict["token"][-1]

    def add_stopword(self, features_dict):
        features_dict["nltk_stopword"] = features_dict["token"] in stopwords.words("english")

    def add_nltk_name(self, features_dict):
        features_dict["is_nltk_name"] = features_dict["token"].lower() in (n.lower() for n in names.words())

    def add_geo(self, features_dict):
        features_dict["is_geo_place"] = bool(GeoText(features_dict["token"]).cities or GeoText(features_dict["token"]).countries)

    def token_features(self):
        """
        Runs each of the token-level functions and mutates self.features
        """
        for features_dict in self.features:
            self.add_case(features_dict)
            self.add_last_char(features_dict)
            self.add_stopword(features_dict)
            self.add_geo(features_dict)


### Functions for output of dev/test data ###

def label_test_data(predicted_classifications, test_fb, output):
    """
    Prints or outputs file of tokens from test data, annotated with named entity tags.
    """
    iter_classifications = iter(predicted_classifications)

    for line in test_fb.orig_data:
        if line == "\n":
            print(line.strip(), file = output) # preserve newlines separating sentences in original data
        else:
            print("{}\t{}".format(line, next(iter_classifications)), file = output)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("training", help = "path to the training data")
    parser.add_argument("test", help = "path to the test data")
    parser.add_argument("trained_glove_model", help = "path to trained glove word vector file")
    parser.add_argument("n_iterations", help = "num iterations for MaxEnt", type = int)
    parser.add_argument("-o", "--output", help = "file path to write to") # optional
    args = parser.parse_args()

    training_fb = FeatureBuilder(args.training, is_training = True)
    training_fb.add_sentence_features()
    training_fb.token_features()

    test_fb = FeatureBuilder(args.test, is_training = False)
    test_fb.add_sentence_features()
    test_fb.token_features()

    classifier = MaxentClassifier.train(training_fb.format_data_maxent(), max_iter = args.n_iterations)

    predicted_classifications = classifier.classify_many(test_fb.features)

    # counter = collections.Counter(predicted_classifications) # see how many tokens in each class
    # print(counter)

    # print(classifier.show_most_informative_features(10))

    if args.output is not None:
        with open(args.output, "w") as f:
            label_test_data(predicted_classifications, test_fb, f)
    else:
        label_test_data(predicted_classifications, test_fb, sys.stdout) # prints results to stdout if no output file is specified

