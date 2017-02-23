import tensorflow as tf
from nets import resnet_v1
from preprocessing import vgg_preprocessing
from ..utils.upsampling import bilinear_upsample_weights

slim = tf.contrib.slim

# Mean values for VGG-16
from preprocessing.vgg_preprocessing import _R_MEAN, _G_MEAN, _B_MEAN


def extract_resnet_v1_101_mapping_without_logits(resnet_v1_101_variables_mapping):
    """Removes the logits variable mapping from resnet_v1_101_8s to resnet_v1_101 model mapping dict.
    Given the resnet_v1_101_8s to resnet_v1_101 model mapping dict which is returned by
    resnet_v1_101_8s() function, remove the mapping for the fc8 variable. This is done because this
    variable is responsible for final class prediction and is different for different
    tasks. Last layer usually has different size, depending on the number of classes
    to be predicted. This is why we omit it from the dict and those variables will
    be randomly initialized later.

    Parameters
    ----------
    resnet_v1_101_variables_mapping : dict {string: variable}
        Dict which maps the resnet_v1_101_8s model's variables to resnet_v1_101 checkpoint variables
        names. Look at resnet_v1_101_8s() function for more details.

    Returns
    -------
    updated_mapping : dict {string: variable}
        Dict which maps the resnet_v1_101_8s model's variables to resnet_v1_101 checkpoint variables
        names without logits layer mapping.
    """

    # TODO: review this part one more time
    resnet_v1_101_keys = resnet_v1_101_variables_mapping.keys()

    resnet_v1_101_without_logits_keys = []

    for key in resnet_v1_101_keys:

        if 'logits' not in key:
            resnet_v1_101_without_logits_keys.append(key)

    updated_mapping = {key: resnet_v1_101_variables_mapping[key] for key in resnet_v1_101_without_logits_keys}

    return updated_mapping



def resnet_v1_101_8s(image_batch_tensor,
                     number_of_classes,
                     number_of_part_classes,
                     is_training):
    """Returns the resnet_v1_101_8s model definition.
    The function returns the model definition of a network that was described
    in 'DeepLab: Semantic Image Segmentation with Deep Convolutional Nets,
    Atrous Convolution, and Fully Connected CRFs' by Chen et al.
    The network subsamples the input by a factor of 8 and uses the bilinear
    upsampling kernel to upsample prediction by a factor of 8. This means that
    if the image size is not of the factor 8, the prediction of different size
    will be delivered. To adapt the network for an any size input use
    adapt_network_for_any_size_input(resnet_v1_101_8s, 8). Note: the upsampling kernel
    is fixed in this model definition, because it didn't give significant
    improvements according to aforementioned paper.

    Parameters
    ----------
    image_batch_tensor : [batch_size, height, width, depth] Tensor
        Tensor specifying input image batch
    number_of_classes : int
        An argument specifying the number of classes to be predicted.
        For example, for PASCAL VOC it is 21.
    is_training : boolean
        An argument specifying if the network is being evaluated or trained.

    Returns
    -------
    upsampled_logits : [batch_size, height, width, number_of_classes] Tensor
        Tensor with logits representing predictions for each class.
        Be careful, the output can be of different size compared to input,
        use adapt_network_for_any_size_input to adapt network for any input size.
        Otherwise, the input images sizes should be of multiple 8.
    resnet_v1_101_8s_variables_mapping : dict {string: variable}
        Dict which maps the resnet_v1_101_8s model's variables to resnet_v1_101 checkpoint variables
        names. We need this to initilize the weights of resnet_v1_101_8s model with resnet_v1_101 from
        checkpoint file. Look at ipython notebook for examples.
    """

    with tf.variable_scope("resnet_v1_101_8s") as resnet_v1_101_8s:

        upsample_factor = 8

        # Convert image to float32 before subtracting the
        # mean pixel value
        image_batch_float = tf.to_float(image_batch_tensor)

        # Subtract the mean pixel value from each pixel
        mean_centered_image_batch = image_batch_float - [_R_MEAN, _G_MEAN, _B_MEAN]

        upsample_filter_np = bilinear_upsample_weights(upsample_factor,
                                                       number_of_classes)

        upsample_filter_tensor = tf.constant(upsample_filter_np)

        upsample_filter_np_part = bilinear_upsample_weights(upsample_factor,
                                                       number_of_part_classes)

        upsample_filter_tensor_part = tf.constant(upsample_filter_np_part)

        # TODO: make pull request to get this custom vgg feature accepted
        # to avoid using custom slim repo.


        with slim.arg_scope(resnet_v1.resnet_arg_scope()):
            logits, end_points = resnet_v1.resnet_v1_101(mean_centered_image_batch,
                                                number_of_classes,
                                                is_training=is_training,
                                                global_pool=False,
                                                output_stride=8)

        downsampled_logits_shape = tf.shape(logits)

        # Calculate the ouput size of the upsampled tensor
        upsampled_logits_shape = tf.pack([
                                          downsampled_logits_shape[0],
                                          downsampled_logits_shape[1] * upsample_factor,
                                          downsampled_logits_shape[2] * upsample_factor,
                                          downsampled_logits_shape[3]
                                         ])

        block2_features = end_points['resnet_v1_101_8s/resnet_v1_101/block2']
        block2_logits = slim.conv2d(block2_features,
                                    number_of_part_classes,
                                    [1, 1],
                                    activation_fn=None,
                                    normalizer_fn=None,
                                    weights_initializer=tf.zeros_initializer,
                                    scope='block2_fc')
        block2_logits_shape = tf.shape(block2_logits)
        block2_logits_upsampled_shape = tf.pack([
                                                 block2_logits_shape[0],
                                                 block2_logits_shape[1] * 8,
                                                 block2_logits_shape[2] * 8,
                                                 block2_logits_shape[3]
                                                 ])

        block2_upsampled_by_factor_8_logits = tf.nn.conv2d_transpose(block2_logits,
                                                                     upsample_filter_tensor_part,
                                                                     output_shape=block2_logits_upsampled_shape,
                                                                     strides=[1, 8, 8, 1])
	
	block3_features = end_points['resnet_v1_101_8s/resnet_v1_101/block3']
        block3_logits = slim.conv2d(block3_features,
                                    number_of_part_classes,
                                    [1, 1],
                                    activation_fn=None,
                                    normalizer_fn=None,
                                    weights_initializer=tf.zeros_initializer,
                                    scope='block3_fc')
        block3_logits_shape = tf.shape(block3_logits)
        block3_logits_upsampled_shape = tf.pack([
                                                 block3_logits_shape[0],
                                                 block3_logits_shape[1] * 8,
                                                 block3_logits_shape[2] * 8,
                                                 block3_logits_shape[3]
                                                 ])

        block3_upsampled_by_factor_8_logits = tf.nn.conv2d_transpose(block3_logits,
                                                                     upsample_filter_tensor_part,
                                                                     output_shape=block3_logits_upsampled_shape,
                                                                     strides=[1, 8, 8, 1])

	part_logits = block2_upsampled_by_factor_8_logits + block3_upsampled_by_factor_8_logits

        # Perform the upsampling
        upsampled_logits = tf.nn.conv2d_transpose(logits,
                                                  upsample_filter_tensor,
                                                  output_shape=upsampled_logits_shape,
                                                  strides=[1, upsample_factor, upsample_factor, 1])

        # Map the original vgg-16 variable names
        # to the variables in our model. This is done
        # to make it possible to use assign_from_checkpoint_fn()
        # while providing this mapping.
        # TODO: make it cleaner
        resnet_v1_101_8s_variables_mapping = {}

        resnet_v1_101_8s_variables = slim.get_variables(resnet_v1_101_8s)

        for variable in resnet_v1_101_8s_variables:

            if 'block3_fc' in variable.name or 'block2_fc' in variable.name:
                continue

            # Here we remove the part of a name of the variable
            # that is responsible for the current variable scope
            original_resnet_v1_101_checkpoint_string = variable.name[len(resnet_v1_101_8s.original_name_scope):-2]
            resnet_v1_101_8s_variables_mapping[original_resnet_v1_101_checkpoint_string] = variable

    return upsampled_logits, part_logits, resnet_v1_101_8s_variables_mapping
