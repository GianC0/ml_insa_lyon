import cv2
import torch
from iou import intersection_over_union


iou_threshold = 0.2
prob_threshold = 0.999 # for 10 iterations 0.999


def pyramid(image, scale=1.5, minSize=(30, 30)):
    # yield the original image
    yield image
    # keep looping over the pyramid
    while True:
        # compute the new dimensions of the image and resize it
        w = int(image.shape[0] / scale)
        h = int(image.shape[1] / scale)
        #image = imutils.resize(image, width=w)
        image = cv2.resize(image, (h,w))
        
        # if the resized image does not meet the supplied minimum
        # size, then stop constructing the pyramid
        if image.shape[0] < minSize[1] or image.shape[1] < minSize[0]:
            break
        # yield the next image in the pyramid
        yield image


def sliding_window(image, stepSize, windowSize):
    # slide a window across the image
    for y in range(0, image.shape[0], stepSize):
        for x in range(0, image.shape[1], stepSize):
            # yield the current window
            yield (x, y, image[y:y + windowSize[1], x:x + windowSize[0]])


def pyramid_sliding_window_detection(net, image, scale, winW, winH, stepSize):
    # Store the initial image before resize, it will be used for the final printing
    faces_img = image.copy()
   
    # loop over the image pyramid
    # all_detected_faces : contains for each pyramid level the scaling factor and the detected faces corresponding to
    # pyramid level
    all_detected_faces = []
    for resized in pyramid(image, scale=scale):
        detected_faces = []
        curr_scale_factor = image.shape[0] / resized.shape[0]
        # loop over the sliding window for each layer of the pyramid
        for (x, y, window) in sliding_window(resized, stepSize=stepSize, windowSize=(winW, winH)):
            # if the window does not meet our desired window size, ignore it
            if window.shape[0] != winH or window.shape[1] != winW:
                continue
            # We use the 36*36 window to match the net's img input size
            resized_tensor = torch.from_numpy(window)
            # Transform the 500*500 (2d) img to a 4d tensor (the additional 2 dimensions contain no information)
            # Alan: I think the 500x500 is wrong, it should be 36x36, but its just the comment that is not updated
            resized_tensor = resized_tensor[None, None, :, :]  # tensor shape is now [1,1,500,500]
            # Feed the network the input tensor
            output = net(resized_tensor)

            # We only register faces with a prob higher than 0.99 to avoid false positives
            # (softmax dim parameter : dim=0->rows add up to 1, dim=1->rows add up to 1)
            # print(output)

            softmax = torch.nn.functional.softmax(output, dim=1)
            if softmax[0][1] >= prob_threshold:
                print(softmax[0][1])
                detected_faces.append((x, y, softmax[0][1].item()))


        #Add the detected faces and the corresponding factors to the all_faces variable
        all_detected_faces.append([curr_scale_factor,detected_faces])
  

    # We use the non_max_supp algorithm to delete overlaping bounding boxes
    # to avoid detecting the same face multiple times
    for j in range(len(all_detected_faces)):
        for i in range(len(all_detected_faces[j][1])): #all_detected_faces[j][1]->detected faces of the i-pyramid-level
            # in this line we both :
            # - change the tuple from a 2d (startX, startY) to a 5d (startX, startY, endX, endY, probability)
            # - multiply each number of the tuple by the current scale factor
            all_detected_faces[j][1][i] = (
                                              all_detected_faces[j][1][i][0] * all_detected_faces[j][0], # startX multiplied with scale
                                              all_detected_faces[j][1][i][1] * all_detected_faces[j][0] # startY multiplied with scale
                                          ) + (
                                            (all_detected_faces[j][1][i][0] + winW)*all_detected_faces[j][0], # startX + width = endX
                                            (all_detected_faces[j][1][i][1] + winH)*all_detected_faces[j][0], # startY + height = endY
                                            all_detected_faces[j][1][i][2] # probability of class being a face
            )
    # Concatenate detected faces into the same array
    clean_version = clean_faces(all_detected_faces)
    print(len(clean_version))
    final_detected_faces = non_max_supp(clean_version)
    print(len(final_detected_faces))
    print(final_detected_faces)
    return final_detected_faces


def non_max_supp(all_detected_faces):
    # [boxes], boxes -> [initX, initY, endX, endY, p]
    all_detected_faces = sorted(all_detected_faces, key=lambda x: x[4], reverse=True)
    faces_after_non_max_supp = []
    while all_detected_faces:
        chosen_box = all_detected_faces.pop()
        # This creates a list of box where everybox is obtained from all_detected_faces only inf the condition is met
        all_detected_faces = [
            box
            for box in all_detected_faces
            if intersection_over_union(
                torch.tensor(chosen_box[:4]),
                torch.tensor(box[:4]),
            ) < iou_threshold
        ]
        faces_after_non_max_supp.append(chosen_box)
    return faces_after_non_max_supp


def clean_faces(faces):
    # [x], x -> [float, [y]], y -> [initX, initY, endX, endY, p]
    cleaned_faces = []
    for x in faces:
        if len(x[1]) == 0:
            continue
        for y in x[1]:
            cleaned_faces.append(y)
    return cleaned_faces
