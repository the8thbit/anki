class Bidirectional:
    def __init__(self, direct = None, inverse = None):
        if isinstance(direct, dict) and isinstance(inverse, dict):
            self.direct = direct
            self.inverse = inverse
            return
        self.direct = dict()
        self.inverse = dict()
        if isinstance(direct, list):
            for counter, value in enumerate(direct):
                self[counter] = value
        

    def getByValue(self, value):
        return self.exchange()[value]

    def __get__(self, key):
        if key in self.direct:
            return self.direct(key)
        raise AttributeError

    def __set__(self, key, value):
        self.direct[key] = value
        self.inverse[value] = key

    def __delete__(self, key):
        del self.inverse[self.direct[key]]
        del self.direct[key]

    def deleteValue(self, value):
        del self.changeSide()[value]

    def exchange(self, key1, key2):
        value1 = self[key1]
        value2 = self[key2]
        self[key1] = value2
        self[key2] = value1

    def exchangeValue(self, value1, value2):
        self.changeSide().exchange(value1, value2)

    def changeSide(self):
        """A Bidirectionnal with key and value reversed. They have both the
        same content.

        """
        return Bidirectionnal(self.inverse, self.direct)
        
    def exchange(self, key1, key2):
        value1 = self[key1]
        value2 = self[key2]
        self[key1] = value2
        self[key2] = value1

    def __contains__(self, key):
        return key in self.direct

    def isValue(self, value):
        return value in self.inverse
