db = connect(process.env.MONGODB_URL);

const cursor = db.stations.find();
while (cursor.hasNext()) {
    const station = cursor.next();
    const oldCollection = `${station._id}`;
    const newCollection = `${station._id}-ttl`;

    db[newCollection].createIndex({time: 1}, {expireAfterSeconds: 60 * 60 * 24 * 10});
    db[oldCollection].aggregate([
        {$set: {receivedAt: {$toDate: {$multiply: ["$time", 1000]}}}},
        {$set: {time: {$toDate: {$multiply: ["$_id", 1000]}}}},
        {$out: newCollection}]
    );
    db[newCollection].renameCollection(oldCollection, true);
}
