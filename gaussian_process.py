'''
Created on Jul 11, 2016

@author: dvanaken
'''

import os.path
import numpy as np

def get_next_config(workload_name, X_client, y_client):
    from analysis.matrix import Matrix
    from analysis.preprocessing import Standardize
    from analysis.util import get_unique_matrix, get_exp_labels
    from experiment import ExpContext, TunerContext
    from globals import Paths
    
    exp = ExpContext()
    tuner = TunerContext()

    # Update client rowlabels
    X_client.rowlabels = get_exp_labels(X_client.data, X_client.columnlabels)
    y_client.rowlabels = X_client.rowlabels.copy()
    print X_client
    print y_client

    print ""
    print "orig X_train shape: {}".format(X_train.data.shape)
    print "orig y_train shape: {}".format(y_train.data.shape)

    # Filter out all metrics except for the optimization metric
    y_client = y_client.filter(np.array([tuner.optimization_metric]), "columns")

    if tuner.map_workload:
        # Load data for mapped workload
        datadir = os.path.join(Paths.DATADIR, workload_name)
        X_path = os.path.join(datadir, "X_data_unique_{}.npz".format(tuner.num_knobs))
        y_path = os.path.join(datadir, "y_data_unique_{}.npz".format(tuner.num_knobs))
        X_train = Matrix.load_matrix(X_path)
        assert np.array_equal(X_train.columnlabels, tuner.featured_knobs)
        assert np.array_equal(X_train.columnlabels, X_client.columnlabels)
        
        # Filter out all metrics except for the optimization metric
        y_train = Matrix.load_matrix(y_path)
        y_train = y_train.filter(np.array([tuner.optimization_metric]), "columns")
        assert np.array_equal(y_train.columnlabels, y_client.columnlabels)
        
        # Concatenate workload and client matrices to create X_train/y_train
        ridge = 0.01 * np.ones((X_train.data.shape[0],))
        new_result_idxs = []
        for cidx, rowlabel in enumerate(X_client.rowlabels):
            primary_idx = [idx for idx,rl in enumerate(X_train.rowlabels) \
                        if rl == rowlabel]
            assert len(primary_idx) <= 1
            if len(primary_idx) == 1:
                # Replace client results in workload matrix if overlap
                y_train.data[primary_idx] = y_client.data[cidx]
                ridge[primary_idx] = 0.000001
            else:
                # Else this is a unique client result
                new_result_idxs.append(cidx)
        
        print ""
        print "new result idxs = {}".format(new_result_idxs)
        if len(new_result_idxs) > 0:
            X_client = Matrix(X_client.data[new_result_idxs],
                            X_client.rowlabels[new_result_idxs],
                            X_client.columnlabels)
            y_client = Matrix(y_client.data[new_result_idxs],
                            y_client.rowlabels[new_result_idxs],
                            y_client.columnlabels)
            X_train = Matrix.vstack([X_train, X_client])
            y_train = Matrix.vstack([y_train, y_client])
            ridge = np.append(ridge, 0.000001 * np.ones(len(new_result_idxs))
    else:
        X_train = X_client
        y_train = y_client
        ridge = 0.000001 * np.ones(X_train.data.shape[0])
    
    # Generate grid to create X_test
    config_mgr = exp.dbms.config_manager_
    X_test = config_mgr.get_param_grid(tuner.featured_knobs)
    X_test_rowlabels = get_exp_labels(X_test, tuner.featured_knobs)
    X_test = Matrix(X_test, X_test_rowlabels, tuner.featured_knobs)
    
    # Scale X_train, y_train and X_test
    X_standardizer = Standardize()
    y_standardizer = Standardize()
    X_train.data = X_standardizer.fit_transform(X_train.data)
    y_train.data = y_standardizer.fit_transform(y_train.data)
    X_test.data = X_standardizer.fit_transform(X_test.data)

    print "X_train shape: {}".format(X_train.data.shape)
    print "y_train shape: {}".format(y_train.data.shape)
    print "X_test shape: {}".format(X_test.data.shape)

    # Make predictions
    ypreds, sigmas, eips = predict(X_train.data,
                                   y_train.data,
                                   X_test.data,
                                   ridge,
                                   tuner.optimization_metric,
                                   tuner.engine)

    ypreds_unscaled = y_standardizer.reverse_transform(ypreds)
    print ""
    for i in range(10):
        print X_test.rowlabels[i]
        #print "y_real={0:.2f}, y_scaled={1:.2f}, sigma={2:.2f}, eip={3:.2f}".format(ypreds_unscaled[i],
        #                                                                            ypreds[i],
        #                                                                            sigmas[i],
        #                                                                            eips[i])
        print "y_real={}, y_scaled={}, sigma={}, eip={}".format(ypreds_unscaled[i],
                                                                                    ypreds[i],
                                                                                    sigmas[i],
                                                                                    eips[i])
        print ""
    

def predict(X_train, y_train, X_test, ridge, metric, eng):
    from common.timeutil import stopwatch

    n_feats = X_train.shape[1]
    X_train = X_train.ravel().squeeze()
    y_train = y_train.ravel().squeeze()
    X_test = X_test.ravel().squeeze()
    ridge = ridge.ravel().squeeze()
    
    print "\nCALL GP:"
    print "X_train shape: {}".format(X_train.shape)
    print "y_train shape: {}".format(y_train.shape)
    print "X_test shape: {}".format(X_test.shape)
    print "Ridge shape: {}".format(ridge.shape)
    
    print "\nStarting predictions..."
    with stopwatch("GP predictions"):
        ypreds, sigmas, eips = eng.gp(X_train.tolist(),
                                      y_train.tolist(),
                                      X_test.tolist(),
                                      ridge.tolist(),
                                      n_feats,
                                      nargout=3)
    ypreds = np.array(list(ypreds), dtype=float)
    sigmas = np.array(list(sigmas), dtype=float)
    eips = np.array(list(eips), dtype=float)
    return ypreds, sigmas, eips
#     end = time.time()
#     print "Done. ({} sec)".format(end - start)
    #print "ypreds initial shape: {}, type: {}".format(len(ypreds),type(ypreds))
    #print "sigmas initial shape: {}, type: {}".format(len(sigmas),type(sigmas))

    #print "ypreds shape: {}".format(ypreds.shape)

    #print "sigmas shape: {}".format(sigmas.shape)
#     print "\nSample preds: {}".format(metric)
#     y_samps = ypreds[:5]*y_std+y_mean
#     for y_samp in y_samps:
#         print "\ty = {}".format(y_samp)

